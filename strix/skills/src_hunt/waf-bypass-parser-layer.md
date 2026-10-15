---
name: "waf-bypass-parser-layer"
description: "waf-bypass-parser-layer"
---

# waf-bypass-parser-layer

# 解析层 WAF 绕过（2025–2026 研究落地）

> **定位分工**：`waf-bypass.md` 管「**payload 本身怎么变形** + 厂商弱点矩阵」；
> 本模块管「**请求结构怎么变形**，让 WAF 和后端解析出两个不同的请求」。
> 两者**叠加**用：先结构绕过（本模块）→ 再 payload 变形（`waf-bypass.md`）→ 还拦才上
> Ghost Bits（`ghost-bits-cast-test.md`）。
>
> **本模块全部手法都不改 payload 一个字**。这是它比传统编码混淆强的地方：
> 任何基于「payload 特征串」的规则（含 ML 分类器）在设计上就看不到攻击。

---

## 0. ★★ 先看这里：**「框架宽容解码」比本文件更容易命中**（2026-09-19 补）

本文件讲的是**解析层差异**（multipart/JSON/XML 边界、HTTP/2 分帧、体积绕过）。
但如果被拦的是**框架特征字面量**（`@type` / `$ref` / OGNL / SpEL / `ac ed 00 05` / `O:N:"…"`），
**先去 `waf-bypass.md` §2.1b** —— 那里有一整类 **比解析层差异更好用** 的手法：

> **WAF 会解标准转义（`\u0040`/`\x40` 都拦），不代表无解。**
> 去读**后端解析器自己的解码实现**，找它「比 WAF 宽容」的点。
> 亲例（fastjson + 腾讯云 WAF，实测通过）：`"\x4Jtype"`（`digits[]` 未占位即 0）、
> `"\x4_type"`、`"\u００４０type"`（全角数字）、`"\u๐๐๔๐type"`（泰文数字）。

完整案例（12+5 组实测矩阵、autotype 状态的无害判别法、报告口径与处置纪律分界线）见
`recon-methodology.md §23`。**判「autotype/白名单开没开」用 `java.lang.String`/`java.lang.Integer` 作探针，
⛔ 不要用真 gadget 类名。**

---

## 1. 一分钟心智模型：双视图差分

```
攻击成功 = WAF 解析出的语义  ≠  后端解析出的语义
                ↓                          ↓
          "这是普通文本/字段"          "这是 SQL/XSS/路径穿越"
```

只要两者不一致，就能「让 WAF 看无害、让后端执行攻击」。**payload 原样保留**。

四层不一致，由浅入深（**按性价比从上往下试**）：

| 层 | 不一致发生在 | 典型手法 | 去哪看 |
|----|-------------|---------|--------|
| **L1** payload 编码 | 同一个串的不同表示 | URL 编码 / 大小写 / 注释 / 关键字拆 | `waf-bypass.md` §2 |
| **L2** 请求体格式 | WAF 与框架的 **body 解析器** | Content-Type 互换 / boundary 续接 / 结构符插 NUL | **本模块 §2** |
| **L3** 协议帧 | WAF 与后端 **HTTP/2 栈** | 流优先级 + 依赖树操纵 | **本模块 §3** |
| **L4** 字符集窄化 | Java `char`→`byte` | Ghost Bits 全字表 | `ghost-bits-cast-test.md` |
| **L5** 传输体积 | WAF 的**检查窗口上限** | Junk padding 把 payload 顶出窗口 | **本模块 §4** |

> L2/L3/L5 的共同点：**都不碰 payload**。所以「payload 特征检测」类防护全部失效，
> 只有「解析器实现对齐」才能修。这是 2025–2026 这批研究的核心结论。

---

## 2. L2 — 请求体解析器不一致（WAFFLED, ACSAC 2025）

**论文**：*WAFFLED: Exploiting Parsing Discrepancies to Bypass Web Application Firewalls*，
Seyed Ali Akhavani 等（Northeastern / Dartmouth），**ACSAC 2025, pp.689-702**，
arXiv:2503.10846（v4 = 2026-03，含 HTML 全文）。

**规模**：实测 **1207 个绕过**，覆盖 **5 个主流 WAF**（AWS / Azure / Cloud Armor /
Cloudflare / ModSecurity）。提出 **24 种攻击类型**（前人工作只有 3 种）。
方法：对**非恶意组件**（header、body 结构元素）做**最小变异**，payload 原样。

### 2.0 先做这一步：Content-Type 互换

**真实世界测量**（PublicWWW 抓 100 个热门「忘记密码」页）：

- >2/3 用 `application/x-www-form-urlencoded`，1/4 用 `application/json`，仅 2 个用 multipart
- **>90% 的站点同时接受 urlencoded 与 multipart 两种编码**（后端不区分）

**所以第一步永远是**：把请求体的 Content-Type 换成另一种格式（Burp Repeater 的
「Change body encoding」一键），**看后端是否照收**。收 → 立刻套下面 12 类 multipart 手法。

### 2.1 multipart/form-data 的 12 类（Table IV）

| # | 类别 | 变异示例（原文形态） |
|---|------|---------------------|
| 1 | Boundary Delimiter Manipulation | `\r\n---boundary`（分隔符前多/少 CRLF） |
| 2 | Content-Disposition 打断 | `content-disposition: form-da\x00a;` |
| 3 | 头部注入进 body | `conten\x00-extra: something` |
| 4 | body 内 Content-Type 微调 | `Content-Type: text/plain\x00; charset=UTF-8` |
| 5 | charset 值改动 | `charset=\x00UTF-8` |
| 6 | 头部行分隔符操纵 | `content-disposition: form-data; name="f1"\x00` |
| 7 | Boundary 分隔符移除 | `---boundary` |
| 8 | 换行移除 | 去掉 header 与 body 之间的 CRLF |
| 9 | 空白操纵 | `Content-Type: \tmultipart/form-data; boundary*0=re;boundary*1=al` |
| 10 | 字段名打断 | `content-disposition: form-data; name="field1\x00"` |
| 11 | Boundary 头部篡改 | `---boundary=value;` |
| 12 | Content-Type 参数微调 | 增删/改参数，WAF 取首参、后端取续接值 |

### 2.2 ★ 最有价值的一枪：RFC 2231 参数续接

**原理**：WAF 只读第一个 `boundary=`；框架支持 RFC 2231 **参数续接**
（`boundary*0=real-; boundary*1=boundary` 会拼成 `real-boundary`）。
→ WAF 按 `fake-boundary` 解析（只看到无害的 value1），后端按 `real-boundary` 解析出 payload。

```http
POST / HTTP/1.1
Host: victim.com
Content-Length: 230
Content-Type: multipart/form-data;
boundary=fake-boundary;boundary*0=real-; boundary*1=
boundary

--fake-boundary
Content-Disposition: form-data; name="field1"

value1
--fake-boundary--
--real-boundary
Content-Disposition: form-data: name="id"

<script>alert(document.cookie)</script>
--real-boundary--
```

**这一枪可复制到任意 multipart 站点**，值得做成固定检查项。

### 2.3 application/xml 的 7 类（Table V）

| # | 类别 | 变异示例 |
|---|------|---------|
| 1 | 额外字段插入 | `<field1>v</field1><field2 attr="history">hi</field2>` |
| 2 | DOCTYPE 闭合混淆 | `<!DOCTYPE BOOK [...]><field1>v</field1>]</BOOK>` |
| 3 | Schema 闭合操纵 | `<genre:schema><field1>v</field1>j</genre:schema>` |
| 4 | 换行滥用 | `\r\nContent-Type: application/xml` |
| 5 | Content-Type 参数移除 | 删掉 header name 只留值 |
| 6 | Content-Type 头替换 | `application/xmlapplication/xml` |
| 7 | 字段错位 | 把字段搬到 WAF 不看的段 |

### 2.4 application/json 的 5 类（Table VI）

| # | 类别 | 变异示例 |
|---|------|---------|
| 1 | Content-Type 移除 | 直接不发 Content-Type |
| 2 | 字段包装操纵 | `{ "field1" \x00: "<script>alert(1)</script>" }` |
| 3 | 双引号替换 | `{ "field1\x00: "<script>alert(1)</script>" }` |
| 4 | 字段名打断 | `{ "f\x00eld1": "<script>alert(1)</script>" }` |
| 5 | Content-Type 参数操纵 | 改 name 参数 |

**JSON 这一组最实用**：Java 系（Jackson/fastjson）对 `\x00` 的处理与 WAF 的 JSON
解析器经常不一致 —— 在 `"字段名"` 与 `:` 之间插一个 `\x00`，WAF 的正则匹配失败
（视作非法 JSON 而跳过检查），而 Jackson 仍能解析出该字段。

### 2.5 五家 WAF 的实测结论

| WAF | 配置 | 是否被绕 |
|-----|------|---------|
| **AWS WAF** | ELB + AWS Managed Ruleset + OWASP CRS 3.0 | **否** —— 唯一没被绕过的 |
| Cloudflare | Pro + CF Managed + CRS | 是 |
| Azure WAF | App Gateway WAF V2 + CRS 3.0 | 是（厂商确认 CRS 3.0 缺陷，后迁 DRS 2.1） |
| Google Cloud Armor | sqli/xss-v33-stable | 是（Tier 1 / P1 / Sev 2） |
| ModSecurity | NGINX + CRS 3.0 PL1 | 是（CRS 3.3 确认全部绕过） |

**关键结论**：**绕过与规则集强弱几乎无关**——payload 完全没混淆，纯粹是解析层漏洞。
AWS WAF 之所以没被绕过，是因为它严格按 RFC 解析。**「严格遵循 RFC」就是防御本身。**

### 2.6 ★ 两个可直接用的 OWASP CRS 官方绕过（CVE，2026 已核实）

> 与 §2.1–2.4 的"通用解析差异"不同，这两条是**CRS 规则自身的实现缺陷**，官方已确认并修复。
> 适用前提：目标 WAF 底层跑 **OWASP CRS** —— 先指纹确认（见 §2.5：ModSecurity / Cloudflare / Azure / GCP 的 CRS 分支都可能命中），再比版本。
> 两条都已实测存在于 NVD / Debian security-tracker / CRS 官方公告，可直接引用。

**① CVE-2026-21876 — multipart 多部分导致链式规则捕获变量被覆盖（CVSS 9.3 CRITICAL）**

- **受影响**：CRS `< 3.3.8` 与 `>= 4.0.0 < 4.22.0`（规则 **922110**，唯一受影响规则）
- **机制**：链式规则中第一条对集合（如 `MULTIPART_PART_HEADERS`）迭代时，捕获变量 `TX:0`/`TX:1` **会被每次迭代覆盖**，只有最后一次的值传给链式后续规则。→ **前面 part 里的恶意 charset 被漏检**（只要后面的 part 带合法 charset）
- **打法**：构造 multipart 请求，**把危险内容放在前面 part**，**最后一个 part 放一个合法 charset** 把 `TX:*` 覆盖掉
- **修复**：CRS 3.3.8 / 4.22.0（2026-01 公布，GHSA-36fv-25j3-r2c5）

**② CVE-2026-33691 — 文件名空白填充绕过上传扩展名检查（CVSS 6.8 / NVD 7.5）**

- **受影响**：CRS `< 3.3.9` 与 `>= 4.0.0 < 4.25.0`
- **机制**：上传规则**不对空白做规范化**就执行扩展名正则，于是 `photo. php`、`shell.jsp␣` 这类写法让 dot-extension 匹配失败（CWE-178）
- **打法**：`filename="shell.jsp␣"` / `filename="shell. jsp"` —— 点号或扩展名前插空白。**注意后端（Tomcat/PHP/nginx）对文件名空白的处理各不相同**，要按目标栈挑位置（点后 / 扩展名后 / 两者都试）
- **修复**：CRS 3.3.9 / 4.25.0（2026-04 公布，GHSA-rw5f-9w43-gv2w）

| CVE | 类型 | 受影响版本 | 修复版本 | 一击动作 |
|-----|------|-----------|---------|---------|
| 2026-21876 | multipart 解析 / 链式规则状态污染 | <3.3.8、4.0.0–4.21.x | 3.3.8 / 4.22.0 | 危险内容前置 + 末 part 放合法 charset |
| 2026-33691 | 文件名空白未规范化 | <3.3.9、4.0.0–4.24.x | 3.3.9 / 4.25.0 | `shell.jsp␣` / `shell. jsp` |

> **踩坑**：两条都**依赖具体 CRS 版本**。修好之后完全失效 —— 所以先确认版本再投入，别把"打不动"当成 payload 写得不好。
> **优先级提示**：只有在目标确实跑 CRS 且版本落在区间内时才值得花时间；若目标用的是**动态防护（瑞数类）或整体加密的业务体**，这两条都用不上（见 §9、§10.1）。

---

## 3. L3 — HTTP/2 流解析混淆（SPCA, WWW 2026）

**论文**：*SPCA: Stream Parser Confusion Attack for WAF Evasion in HTTP/2*，
Kyungrok Choi / Woonghee Lee / Junbeom Hur（Korea Univ. / Dongguk Univ.），
**WWW 2026, pp.3229-3239**，DOI 10.1145/3774904.3792517。

**一句话**：**只操纵 HTTP/2 的流优先级权重与依赖树，不改任何 header/body 字节**，
就能让 WAF 漏检。**完全符合 RFC**，所以不是畸形包。

### 3.1 机制

WAF 与后端 HTTP/2 栈对「流依赖 + 优先级」的处理顺序不同：
WAF 按它自己维护的流树决定**检查顺序/是否检查**，后端按另一套顺序**组装并处理**。
当结构足够复杂时，WAF 的检查覆盖不到实际承载 payload 的那个流。

**三种流拓扑（论文定义，均取自真实调度模式）**：

| 拓扑 | 结构 | 单拓扑绕过率 |
|------|------|-------------|
| **skewed** | 倾斜树 | 49.66% |
| **k-ary** | k 叉树 | 44.62% |
| **unbalanced** | 不平衡树 | 46.38% |
| **三拓扑并发** | 组合投递 | **>89%（平均）** |

**测试面**：13 个商用/开源 WAF × 20 个后端 Web 框架，黑盒。

### 3.2 实战意义与边界

- **前提**：目标必须真的用 **HTTP/2**（h2 协商成功），且 WAF 支持并解析流优先级。
- **测试成本高**：需要能构造任意 h2 帧序列的客户端（不是 curl 能干的）。
  先用 `h2spec` / 自写 h2 客户端确认可协商，再考虑复现。
- **和走私的区别**：SPCA 不产生 desync 多请求，它只是「让 WAF 看漏」，
  所以**不在「HTTP/2 走私不交」的范畴内** —— 它是绕过手法，服务于把 payload 送进去。
- **落地建议**：作为**最后的逃生门**。L1/L2/L5 都试完仍被拦、且确认是 h2 链路时再上。

---

## 4. L5 — 体积绕过 / Payload Padding（nowafpls 系）

**原理**：**几乎所有 WAF 只检查 body 的前 N KB**，超出部分直接透传。
在 payload **前面**塞垃圾数据把 payload 顶出检查窗口即可。

```
POST /api/endpoint HTTP/1.1
Content-Type: application/json

{"userSession":"<随机 128KB 垃圾>","username":"admin' OR 1=1--"}
```

### 4.1 各 WAF 的 body 检查上限（nowafpls README 原始表）

| WAF 厂商 | 最大 body 检查尺寸 |
|---------|------------------|
| Cloudflare | 128 KB（ruleset engine；企业版可达 500 MB） |
| AWS WAF | **8 KB – 64 KB**（按服务可配） |
| Akamai | 8 KB – 128 KB |
| Azure WAF | 128 KB |
| Google Cloud Armor | **8 KB**（可提到 128 KB） |
| Fortiweb | 100 MB |
| Barracuda | 64 KB |
| Sucuri | 10 MB |
| Radware AppWall | up to 1 GB |
| F5 BIG-IP WAAP | 20 MB（可配） |
| Palo Alto | 10 MB |

> **8 KB 那两行是金矿**：AWS WAF / Cloud Armor 默认只查 8 KB。
> 一个 9 KB 的 body 就可能整段免检。**遇 WAF 先试体积，成本最低、收益最高。**

### 4.2 工具

| 工具 | 形态 | 特点 |
|------|------|------|
| `assetnote/nowafpls` | Burp (Jython)，~80 行 | 原版；支持 urlencoded/JSON/XML；右键插入固定量 junk |
| `irwankusuma/nowafplsV2` | Burp（Java Montoya / Python 双版） | **9 种 Content-Type 家族**（+GraphQL/YAML/CSV/NDJSON/text-plain）；**反指纹 junk**（2,328 个真实参数名前缀 + 随机后缀，避免被一条规则封掉 `bullet=`）；支持 DAST；检测 chunked 时自动跳过（体积绕过与 chunked 不兼容）；JSON 缩进保持、BOM 处理 |

**反指纹这点很重要**：原版/同类扩展用固定串（`bullet`、`dummy123`、`aaaa...`），
管理员发现后**写一条规则就永久封死**。V2 每次请求换真实感参数名，无法用单条规则拦。

### 4.3 关键限制

- **与 `Transfer-Encoding: chunked` 不兼容** —— chunked 下 body 尺寸语义不同，体积绕过失效。
  遇到 chunked 就别用这条（V2 已自动跳过，原版会发出畸形包）。
- **必须真的把 payload 放后面**：有些 WAF 是「超限即拦截」而非「超限即放行」，
  先用一个已知会被拦的 payload 测「加大体积后是否变成放行」。
- 判断要**看响应差异**，不能只看 200（WAF 可能 200 但静默剥掉了 payload）。

---

## 5. 对抗性 payload 生成（BWAFSQLi / GSQLi）

> 这两篇是**方法论**（自动化搜索引擎），不是可直接抄的 payload 表。
> 价值在于：告诉我们「手工试几个变体」远远不够，**要按变异空间系统搜**，
> 以及给了两个已验证有效的**新手法**。

### 5.1 BWAFSQLi（ACM TOSEM, accepted 2026-01-05, DOI 10.1145/3788286）

**问题**：现有对抗式 SQLi 生成有四个毛病 —— payload 质量/多样性差、变异策略不足、
**变异后语义不等价**（变了但打不通）、搜索效率低。

**做法**：
- **收敛因子引导的上下文无关文法（CFG）** 生成高质量种子：覆盖 **18 种攻击场景**，
  针对 **58 条规则**
- 对检测到的 token 应用 **26 条规则 / 15 种变异策略**，保证**语义等价**
- **两个新手法**：`Quotation Mark Encoding`（引号编码）、`Comment Extension`（注释扩展）
- **变异策略选择机制**：衰减因子 + 历史数据表 → 自适应多位置变异，**减少请求数**

**结果**：11 个 WAF（3 灰盒 / 8 黑盒），把 WAF 的**漏报率（FNR）最高提升 93.39%（灰盒）
/ 58.49%（黑盒）**，用更少请求超过 3 个 SOTA。七个预处理防御可完全压住。

**可落地的一句话**：**别手工试，按「引号编码 + 注释扩展」两个方向 + 多位置组合系统地搜**，
并记录每次尝试（历史表）避免重复。

### 5.2 GSQLi（ICCAI 2025, pp.788-793, DOI 10.1109/ICCAI66501.2025.00122）

**做法**：用 **GAN** 对原始 SQLi payload 做多次变异，生成「检测器认不出、但仍能打通」的样本。
**结果**：绕过了基于 ML 的攻击检测器 **和 ModSecurity**（真实 WAF）。

**意义**：**ML 检测器并不比规则强** —— 对抗样本同样能吃。别因为目标上了「AI WAF」就放弃。

### 5.3 对实战的启示

| 结论 | 行动 |
|------|------|
| 变异空间很大，手工试 3-5 个不够 | 建**变异矩阵**：位置 × 编码 × 注释 × 大小写，系统遍历 |
| 语义等价是硬约束 | 每个变体**必须真的能打通**才算数（用差分验证，别只看未拦截） |
| 记录历史可省请求 | 同一参数别重复试同一变体；把「已试」落盘 |
| ML 也一样脆 | 对 ML WAF 直接上对抗变体，不必绕道 |

---

## 6. 工具链：wafrift（Rust，BETA）

**仓库**：`github.com/santhreal/wafrift`。定位：**在 sqlmap / Burp / ffuf 被拦时插入的规避层**。

### 6.1 有用的能力

| 命令 | 作用 |
|------|------|
| `wafrift detect` | 四维指纹：HTTP 头+体（160+ 规则）/ DNS CNAME（37 规则）/ 反向 DNS / BGP ASN |
| `wafrift discover` | 解析 OpenAPI / GraphQL introspection / 参数挖掘 → 去重注入点 |
| `wafrift evade` | **离线**变异器：输入 payload，输出 N 个变体（不需目标） |
| `wafrift scan` | 实弹：多信号预言机分类 `block/bypass/challenge/rate-limit`，出 JSON 报告 |
| `wafrift bypass-probe` | 差分认证/路径/方法绕过扫描（230 个认证绕过头探针） |
| `wafrift smuggle*` | 走私家族（CL.TE / TE.CL / H2 desync 等 25+ 变体）+ TCP 分段重叠 |
| `wafrift compress` | 压缩混淆（gzip/deflate/**brotli** 链式包裹）—— 多数 WAF 不解 brotli |
| `wafrift distill` | Zeller ddmin 求**最小可用绕过载荷** |
| `wafrift-proxy` | 前向代理，串 Burp/mitmproxy；可 `--tls-impersonate chrome131` 换 TLS 指纹 |

### 6.2 两个必记的设计点

1. **基因库（gene-bank）**：获胜变体持久化到 `~/.wafrift/genomes/<waf>.json`，
   下次对同一 WAF 零发现启动 → **绕过经验要落盘复用**（和我们自己的短表一个道理）。
2. **差分基线（`--differential-baseline`）**：只有「未绕过的基线请求确实被拦」时才记绕过。
   **杜绝「端点本来就没管控 → 返回 200 → 误判为绕过」**。
   → 这条直接对应我们短表里的「假进度」禁项，是**判据设计**的正确做法。

### 6.3 实测数据（README 自报，ModSecurity + CRS，557 案例 × 10 攻击类）

| 偏执级别 | 变体数 | 绕过数 | 率 | 案例 ≥1 绕过 |
|---------|-------|-------|----|------------|
| PL=1 | 46k | 16.7k | 36% | 557/557（100%） |
| PL=4 | 60k | 16.3k | 27% | 557/557（100%） |

**读法**：这是**搜索预算结果**（不是一键搞定），且 **PL1 与 PL4 差不到 10 个点** ——
再次印证「偏执级别调高帮助有限，解析层不一致才是缺口」。
**注意**：数字来自作者自建 CI 环境，不是第三方复现；引用时要标注来源。

---

## 7. L6（后渗透）— 多层编码外泄，以 F5 为例

**论文**：*Bypassing F5 WAF for Data Exfiltration during Post-Exploitation*，
Bichnigauri / Shonia / Shonia（Georgian Technical University），
MCAICT Transactions Vol.4 (2025), pp.89-93。

**场景**：已经打进去了，要**把数据带出来**，但出网流量过 WAF/IDS。
（对应我们自己：`hunt-iter` 里「打穿后」的阶段，属**证明型**而非**拖库型**用法。）

**手法**：**三层编码叠加** —— `Base64 → 反转（Reversal）→ Hex`，
**请求里的命令**和**响应里的被窃数据**都编码。

- 命令侧：`cat /etc/passwd | base64 | rev | xxd` → 全 ASCII 无敏感关键字
- 数据侧：受害数据编码后经 HTTP 响应带出，静态规则集看不到敏感模式

**论文强调的局限**：这种方法只能骗**静态签名**；对**动态分析 / 参数校验 / 行为异常检测**
无效。作者建议的后续方向是自定义加密与非对称加密（更彻底）。

**红线提醒**：本文用于**证明可达性 + 最小样本**，**禁止真拖库**（详见 `../01` 红线、
`03` 报告规范）。本条只作为「绕过外泄检测」的技术储备。

---

## 8. 实战决策树（进站遇 WAF 就照这个走）

```
请求被 WAF 拦了
│
├─ 0. 先确定拦的是什么层
│   ├─ 静态规则 / ML 检测器（返回 403/自定义拦截页）→ 本模块全套适用
│   └─ 动态 JS 挑战（412 + $_ts/_$$q()、动态 cookie、动态 URL 参数）→ §9，本模块大部分不适用
│
├─ 1. 【成本最低】体积绕过（L5）
│   ├─ 目标是 AWS WAF / Cloud Armor？→ 默认只查 8KB，直接超大体积试
│   └─ 不是 chunked 且原 payload 被拦？→ 前置 junk 再发（注意「超限即拦」的配置）
│
├─ 2. 【性价比最高】Content-Type 互换 + L2 结构变异
│   ├─ 换 body 编码（urlencoded ↔ multipart ↔ json），看后端收不收
│   ├─ multipart → 先打 RFC2231 boundary 续接（§2.2）
│   ├─ JSON → 字段名与冒号间插 \x00（§2.4）
│   └─ XML → 额外字段 / 闭括号操纵（§2.3）
│
├─ 3. 还是拦？→ 上 L1 payload 变形（waf-bypass.md §2）
│   └─ 按栈选：SQL 注释/函数替换；XSS 换标签事件；命令注入用变量拼接
│
├─ 4. 是 Java 栈？→ 上 L4 Ghost Bits（ghost-bits-cast-test.md）
│   └─ 一句话：`chr((k<<8)|目标字节)`，255 个候选字轮换用
│
├─ 5. 确认是 HTTP/2 链路？→ L3 SPCA（§3）
│   └─ 成本高，作最后逃生门
│
└─ 6. 始终不通
    ├─ 找源站 IP 直连（绕过 WAF 本身，见 waf-bypass.md §5.5）
    ├─ 换个等价端点 / 换 METHOD / 换参数位置
    └─ 记「本次未绕过 + 已试矩阵」落盘，别空转
```

**变异矩阵模板**（照着填，避免漏项）：

| 维度 | 取值 |
|------|------|
| 投递位 | query / body / header / path / cookie / 文件名 |
| 体格式 | urlencoded / multipart / json / xml / text-plain |
| 结构变异 | boundary 续接 / NUL 插入 / 换行移除 / 参数续接 |
| 体积 | 原样 / 9KB / 64KB / 128KB 前置 junk |
| 编码 | 单/双/三重 URL / Unicode / HTML 实体 / Ghost Bits |
| payload 变体 | 按类型 3-5 个语义等价写法 |

---

## 9. ★ 关键区分：静态 WAF vs 动态防护（瑞数类）

**本模块 §2–§7 全部针对「检查型 WAF」**（在网关侧解析请求、按规则/模型判定）。
**它们对「动态 JS 挑战」型防护基本不适用。** 必须分清，否则白费力气。

| 维度 | 静态 WAF（本模块适用） | 动态防护（瑞数/顶象/JA3 类） |
|------|---------------------|---------------------------|
| 拦什么 | 请求内容（参数、body、header） | **客户端是不是"真的浏览器"** |
| 响应特征 | 403 / 自定义拦截页 | **412 Precondition Failed** + `$_ts`/`_$$q()` + 动态 meta 令牌 |
| 凭证 | 无状态，看内容 | **动态 cookie（JS 计算）+ 动态 URL 参数** |
| 绕过思路 | 改请求结构（本模块） | **让 JS 真正执行**（真实浏览器、补环境、逆向算法） |
| 改 payload 有用吗 | 有用（核心） | **没用** —— 它不看 payload |
| 加体积有用吗 | 有用（L5） | **没用** |

**实践结论（189.cn 实测教训）**：

1. **先判型**：看是否 412 + 动态令牌。是 → 走动态防护路线，**不要浪费 L1–L5**。
2. **动态防护下唯一正确的高性价比动作**：
   - **测静态资源是否豁免**（`.js/.css`）→ 豁免就能拿全量前端代码做纯分析
   - **找 API 白名单**（首页必需接口常被放行）
   - **上真实浏览器**（用户本机 Chrome + `--remote-debugging-port` + `connect` 接入）
3. **白名单前缀匹配 ≠ 可利用**：即使白名单是前缀匹配、且双编码能"过"防护层，
   也**必须拿到目标接口的真实响应**才算绕过。拿到 400/404 只说明过了第一层
   （189.cn 就是 `%252f` 过了防护但被 Tomcat `allowEncodedSlash=false` 拒）。
4. **想通用化地打动态防护**：要么补环境/逆向它的 JS（成本高、易失效），
   要么用真实浏览器做「请求转发器」（见 §10）。

> **动态防护的完整实操（识别/版本判定/三件套/四条路线/具体环境补全清单）已独立成篇：**
> **→ `river-security-bypass.md`**。本节只做「判型」，一旦判定是动态防护就转过去。

---

## 10. 动态防护下的实操替代方案（本模块的补充工具箱）

> 当目标上了动态防护、而你需要发构造请求时，按性价比：

| 方案 | 做法 | 适用 |
|------|------|------|
| **浏览器当请求转发器** | 真实浏览器打开目标站 → 在页面上下文用 `XMLHttpRequest`/`fetch` 发请求（带齐动态 cookie/参数）→ 读响应 | 首选。浏览器已过挑战，同源/跨域都行（注意 CORS 配置） |
| 明文 body 探测 | 有些动态防护只对「特定特征」放行；试「不加密/不带签名的裸 body」能否直达应用层 | 成本极低，先试 |
| 白名单前缀探针 | 已知白名单路径 + 后缀变体（`.doX`、`.do/`、`.do;x`） | 用于**确认白名单匹配方式**，不指望直接打通 |
| 补环境执行它的 JS | 提取挑战 JS → Node 里补 `window/navigator/document` → 算出 cookie 与动态参数 | 成本高；仅当需要长期自动化时投入 |
| 用户手工补抓包 | 让用户在自己浏览器里操作目标功能，再导出抓包 | 分析用足够，验证越权仍受限 |

**在页面上下文发请求的最小骨架**（真实浏览器内）：

```js
function post(url, bodyObj, headers) {
  return new Promise((res) => {
    const x = new XMLHttpRequest();
    x.open("POST", url, true);
    x.withCredentials = true;                       // 带上会话/dynamic cookie
    Object.keys(headers || {}).forEach(k => x.setRequestHeader(k, headers[k]));
    x.onreadystatechange = () => { if (x.readyState === 4) res({ s: x.status, t: x.responseText }); };
    x.onerror = () => res({ s: -1, t: "xhr error" });
    x.send(JSON.stringify(bodyObj));
  });
}
```

> 选 `XMLHttpRequest` 而不是 `fetch`：多数动态防护 hook 的是 XHR，
> 用 XHR 才能让它的注入逻辑生效（补上动态 URL 参数）。

### 10.1 ★★ 前端整体加密的业务体 = 内容型 WAF 的天然盲区

> **2026-09-15 189.cn 实测。** 这条不是"绕过技巧"，而是**架构性事实**——比任何变形手法都彻底，值得在拿到前端加密逻辑后第一时间验证。

**机制**：站点若把业务请求体**整体加密**（典型形态 `{"param": base64(AES-CBC(业务JSON)), "key": base64(RSA({key,iv}))}`），
那么 WAF 收到的 body 只有两段 base64 密文，**没有任何明文关键词可供匹配**——正则、语义分析、机器学习特征全部失效。

**189 实测对照**（用**免防护接口** `recPos/getRecPosInfo.do` 做对照，绕开动态挑战只观察 WAF 行为）：

| Payload | 明文发送 | 放进正常加密体发送 |
|---|---|---|
| `index_banner`（基线） | 200 | 200 |
| `index_banner'`（单引号） | **200（不拦）** | 200 |
| `' AND '1'='1` | **400 拦** | **200 放行** |
| `' UNION SELECT 1,2,3--` | **400 拦** | **200 放行** |
| `<script>alert(1)</script>` | **400 拦** | **200 放行** |
| `../../../../etc/passwd` | **400 拦** | **200 放行** |
| `index_banner;cat /etc/passwd` | **400 拦** | **200 放行** |
| `'A' × 9000`（体积） | 200（**不拦体积**） | 200 |

**关键证据**：XSS 那条的错误码从 `S_WEB_0104` 变为 `S_WEB_0102` —— **错误码变化证明 payload 已解密抵达业务层**，
拦截者已从"防护层"换成"业务逻辑"，这才是真正的穿透。

**必须配套的判据（别搞混）**：

| 防护层 | 检查对象 | 解法 | 二者关系 |
|---|---|---|---|
| 动态挑战（瑞数类，412） | 请求**来源合法性**（三件套） | 借用已过挑战的真实浏览器（见 §10 表格） | **互不替代** |
| 内容型 WAF（400 + 空 body） | 请求**内容特征** | 放进加密体，无需任何变形 | 独立性：换通道**不能**解决这一层 |

**踩坑提醒**：

1. **这层免疫只在"整体加密"时成立**。若站点只加密个别字段（或对某些接口 `enableDecrypt:false` 且请求也明文），WAF 依旧看得见。
   拿到前端加密逻辑后，先确认**目标接口是否走加密体**（看 `enableEncrypt` 开关，别被 `enableDecrypt:false` 误导——后者只关响应解密）。
2. **服务端解密后仍有自己的校验**。189 的 `0102` vs `0104` 差异就是证据；payload 进得去 ≠ 一定注入成功，仍要按正常流程做差分验证。
3. **探 WAF 存在性的正确姿势**：优先找该站的**免防护接口**直连打明文 payload 做对照——既能确认 WAF 拦什么（189 拦 `AND`/`UNION`/`<script>`/`../`/`;cat`，但**放行单个单引号**），又不会消耗动态挑战配额。
   **别拿受保护接口去测 WAF**——412 会把 WAF 的响应完全遮住，得到的结论是错的。
4. 单个单引号放行、`AND`/`UNION` 被拦，说明是**关键词/表达式级**规则而非全字符级——意味着 WAF 的绕过空间本来也存在；
   但在有加密体的情况下，**没必要投入变形成本**。
5. ★★ **反例：整体加密体也可能"解密后再过滤"（2026-09-15 sn.189.cn 实测，同一域名下另一套网关）**。
   同样把 payload 塞进正常加密体（`{"encryptedData":SM2(hex(JSON))}` + `access`/`reqAccess` 头），这次**没被放行**：
   网关解密后对业务参数做了二次内容校验，**命中单引号**就返回自定义码 **`999 入参中有非法字符`**；
   而 `<script>`、`../`、`;cat` **全部放行**到业务层（业务层只当参数非法，返 `500 查询失败`）。
   → **结论**：`加密体免疫` 是**部署决定的，不是架构保证的**。只要网关在解密后插了校验（网关插件 / 框架过滤器 / 参数白名单），密文拦不住它。
   → **探法**：先拿**单引号**当最小探针。放行 → 按本节"无需变形"走；返回自定义拦截码 → 该站有**解密后校验**，须转"按字符集/语法绕过"，**别默认免疫**。
   → **别误判**：只拦单引号 ≠ WAF 很强。本例只拦这一个字符，`<script>`/穿越/命令连接符全放行——它拦的是"最小 SQLi 特征"，不是通用内容过滤，
     所以 XSS / 路径穿越 / 命令注入这几类**并没有被这层拦住**（打不打得动是另外一回事）。
6. ★★ **"解密后过滤"这一层怎么绕（2026-09-15 sn.189.cn 实测四类手法）**。前提：过滤**作用在 JSON 解析后的参数值上**（`\u0027` 也被拦即为此证）。
   按性价比实测结果：

   | 手法（对应本模块章节） | 结果 | 机制 |
   |----------------------|------|------|
   | **数组 / 对象包裹**（类型不一致） | ✅ **过了过滤** | 过滤器只扫**字符串标量**，不递归数组/对象元素：`{"k":["1' OR 1=1"]}` 不再触发 999 |
   | Content-Type 互换（§2.0） | ⛔ 无效 | 过滤与 CT 无关，json / text-plain / urlencoded / 无 CT 全一样拦 |
   | 重复 JSON 键 | ⛔ 无效 | 过滤器与业务**都取最后一个**，没有视图差 |
   | 结构符插 NUL（§2.4） | ⛔ **通道不可用** | 见下条"不补零 hex" |
   | 体积绕过（§4 L5） | ⛔ 无效 | 加额外字段直接 400（严格反序列化 `FAIL_ON_UNKNOWN_PROPERTIES`）；512B 即崩 |
   | **Ghost Bits**（`ghost-bits-cast-test.md` §3/§4） | ⛔ **失效** | 见下条"hex 字节透明" |

   **★ 结论 1 — 数组/对象包裹是"值级黑名单"的结构性缺口**：
   只要过滤器是"遍历参数字符串做黑名单匹配"，`{"k":["<payload>"]}` 就能把 payload 藏进数组元素绕过它。
   **但**按 §10.1 开头那条原则，**过防护层 ≠ 打通接口**：本例业务层**不把数组转成 String**（返 `500 查询用户信息失败`），
   且应用层**还有第二道**"入参中有非法字符"校验把 `'` 拦住 ⇒ 绕过了网关那层，仍没打通。
   所以这条的价值是"**判据**"：先确认业务层认不认数组/对象类型（`{"k":["<合法值>"]}` 能返正常数据吗），认了才值得往下打。

   **★ 结论 2 — hex 编码通道下 Ghost Bits 必然失效**（新，很有用）：
   `charCodeAt().toString(16)` 这种"逐字符 hex 拼接"编码是**字节透明**的——ghost 字符 `chr((k<<8)|0x27)` 编码出的 hex 里，
   **低字节 `0x27` 原样出现在解码后的字节流里**。过滤器只要在字节层搜一次 `0x27`/`0x3C` 就命中（实测：ghost 引号 `U+1027` 单发 → 999 被拦）。
   → 走 hex / 裸字节 / 任何字节透明通道时，**别指望 Ghost Bits**；它只在"字符层被检查、字节层才收窄"的路径上有效。

   **★ 结论 3 — 认"两层过滤器"要看 code 的类型与字段名，别被同一句文案骗了**：
   同一个站可能有两层内容校验，**文案一样但结构不同**：
   - 网关层：`{"code":"999","message":"入参中有非法字符"}` ← `code` 是**字符串**
   - 应用层：`{"code":500,"errorMsg":"入参中有非法字符","isSuccess":false}` ← `code` 是**数字**
   把两层混为一谈，会误判"payload 到底过没过网关"。

   **★ 结论 4 — "不补零 hex"通道会让含 NUL 的手法失效**：
   `charCodeAt(a).toString(16)` 对码位 `< 0x10` 只产出**1 位** hex（`\x00`→`"0"`、`\n`→`"a"`），
   而服务端按 2 字符 1 字节配对解码 ⇒ **从该字符起整段错位**。所以 `\x00` 类 JSON 手法在这条通道上根本发不出去。
   同理，Ghost 字符也必须挑**高字节非零**的（`k ≥ 0x10`，如 U+1027）才是 4 位 hex，否则 3 位 hex 一样错位。

---

## 11. 防御视角（给防守方/写报告用）

| 措施 | 说明 |
|------|------|
| **WAF 与后端用同一套解析器** | 最根本。解析结果不一致是这一整类攻击的根因 |
| **严格遵循 RFC** | AWS WAF 唯一未被绕，就是因为它严格、不做"宽松解析" |
| **多视图归一化后再匹配** | 原串 + URL 解码后 + `&0xFF` 窄化后 + NFKC 后，四视图都要看（`ghost-bits-cast-test.md` §10） |
| **body 检查窗口要够大** | 至少覆盖应用的真实上限；否则 8KB 之后全是盲区 |
| **拒绝畸形结构** | 含 NUL 的 header/body、参数续接、非 RFC 的 boundary，直接 400 |
| **别指望提高偏执级别** | wafrift 数据显示 PL1 vs PL4 绕过率只差约 9 个点 |
| **记录并告警拦截** | 绕过尝试在日志里可见（畸形结构、CJK 出现在协议字段位置） |

---

## 12. 一句话

**先判 WAF 类型**：静态检查型 → 按「体积（§4）→ 体格式互换+结构变异（§2）→
payload 变形（waf-bypass）→ Ghost Bits（Java）→ SPCA（h2）」的顺序打，**全程尽量不改 payload**；
动态 JS 挑战型（412 + `$_ts`）→ **放弃 L1–L5**，转「测静态资源豁免 + 找白名单 + 上真实浏览器」（§9/§10）。

---

## REFERENCE（全部已核实存在）

| 研究 | 出处 | 关键数字 |
|------|------|---------|
| WAFFLED | ACSAC 2025, pp.689-702；arXiv:2503.10846 | 1207 绕过 / 5 WAF / 24 类；>90% 站点接受 CT 互换 |
| SPCA | WWW 2026, pp.3229-3239, DOI 10.1145/3774904.3792517 | 13 WAF × 20 框架；单拓扑 44–50%，三拓扑并发 >89% |
| BWAFSQLi | ACM TOSEM, 2026-01-05, DOI 10.1145/3788286 | FNR +93.39%(灰盒) / +58.49%(黑盒)；11 WAF |
| GSQLi | ICCAI 2025, pp.788-793, DOI 10.1109/ICCAI66501.2025.00122 | GAN 生成绕过 ML 检测器 + ModSecurity |
| nowafpls | github.com/assetnote/nowafpls | WAF body 上限表（AWS/Cloud Armor 8KB） |
| nowafplsV2 | github.com/irwankusuma/nowafplsV2 | 9 种 CT 家族；反指纹参数名；DAST 支持 |
| wafrift | github.com/santhreal/wafrift | 基因库 / 差分基线；ModSec PL1 36%、PL4 27% |
| F5 外泄绕过 | MCAICT Trans. Vol.4 (2025), pp.89-93 | Base64→rev→hex 三层编码（仅骗静态签名） |
| Ghost Bits / Cast | Black Hat Asia 2026 | 见 `ghost-bits-cast-test.md`（本库已有） |

---

## 13. ★ 实测补充：阿里云 WAF（2026-09-15 联通小程序）

目标指纹：拦截页 `<!doctypehtml>` + **`data-spm="a3c0"`** + **2657 字节** + HTTP **405**（注意是 405 不是 403）。
判型：**静态检查型**（本模块适用）；`/zz_nonexist` 返回 404、`/.env` 返回 405 ⇒ WAF 专拦敏感路径，二者可区分。

### 13.1 实测结论矩阵

| 手法 | 阿里云 WAF 结果 |
|------|----------------|
| L5 体积：前置 9KB / 64KB / 128KB junk | 🔴 **全拦**（检查窗口 >128KB） |
| L2.0 CT 互换（form / text-plain / 无 CT） | 🔴 全拦；且正常值换 form 返 **415** ⇒ 后端只吃 JSON，此路本就不通（**先验后端收不收再投入**） |
| L2.0 multipart / RFC2231 boundary 续接 | 🔴 拦 / 415（后端不解析 multipart） |
| L2.4 JSON `\x00` 插字段名·冒号间·值后 | 🔴 **全拦**（WAF 与后端 JSON 视图一致，WAFFLED 该组不成立） |
| L1 `&&`、`%26%26`、`\|\|` | 🟢 **穿**（405→200 到业务层） |
| L1 双写 `ANANDD` | 🟢 **穿** |
| L1 注释 `A/**/ND` | 🟢 穿（部分接口） |
| L1 全角 `ＡＮＤ` | 🟢 **穿** |
| L1 `%41%4E%44`（AND 的 URL 编码） | 🔴 拦（WAF 先 URL 解码再匹配） |
| L1 `aNd` 大小写 | 🔴 拦（大小写不敏感） |
| L1 `or` / `%09AND%09` / `+AND+` | 🔴 拦（`+`/`%09` 按空格归一化） |
| 位置：query / GET | 🔴 拦 |
| **自定义请求头** | 🟢 **WAF 不检查自定义头**（但业务层不读就没用，除非业务确实读该头） |
| 敏感路径 13 种变形（`//`、`/./`、`;`、`/..;/`、`%2e`、`%252e`、全大写…） | 🔴 全拦 |

### 13.2 两条必记的判据

1. **`%00` 的 400 不是绕过**：`/.env%00` 若返 `400 Bad Request`（Tengine/nginx 版式），**必须先打 `/zz_nonexist%00` 做对照** —— 若同样返 400，说明是 **HTTP 解析层拒 NUL**，请求根本没到 WAF/应用。别把它当成"WAF 放行"。
2. **该 WAF 有行为学习/自动拦截**：同一来源高频注入特征探测后，**原本正常的请求也开始被拦**（实测 `phone=<正常号码>` 由 200 变 405、换票接口返非 JSON）。
   → **测试到一定量就要收手**，否则会消耗用户 IP 的可信度（用户还要正常用该 App）。
   → 判据：把"已知正常的请求"当**哨兵**，哨兵被拦就说明环境已被封，此时任何结论都不可信（对应本模块 §6.2 的差分基线原则）。

---

## 14. ★ 实测补充：SHEIN 自研 WAF「GSRM Security」（2026-09-17，dotfashion.cn / sheincorp.cn）

> 与 §13（阿里云）并列的**第二份实测矩阵**。GSRM 的特点：单点触发阈值不算低，
> 但一旦触发就是 **IP 级 + 跨域生效**的长时间封禁，而且**它盯的是行为不是内容**。

### 14.1 指纹（★ 必须记住这张页）

拦截页特征：**2662 字节** / `<title>Error Page</title>` / `STATUS:403` /
`The server's gone missing.` / `EVENT ID:<长数字>` / `Please contact GSRM Security support for more information.`

**★ 判别铁律**：这张页**不是业务 403**。原始资产里 `help.sheincorp.cn` 从扫描器抓下来时**就已经是这张页**
⇒ 它当时已处于拦截态。**任何「403 = 不可访问」的判断之前，先确认不是这张页**，
否则整份结论全错。（注意与 §13 阿里云那张 `data-spm="a3c0"` 的 2657 字节页分开记，两者都极易混进业务响应里。）

### 14.2 判型

**静态检查型**（本模块 §2–§7 适用）。无 412、无 `$_ts`、无动态 cookie ⇒ **不是瑞数类**，
**不要**浪费时间在"让它的 JS 真正执行"上。

### 14.3 实测矩阵

| 维度 | 实测结果 |
|---|---|
| **触发维度** | ★ **是「行为 + 速率」，不是「内容」**：正常业务路径 `POST /print` 连发 50+ 次**完全没事**；对同一主机打 ~16 个异常路径（WebLogic 入口枚举）+ 1 次 T3 握手 → **立即全域封禁** |
| **封禁粒度** | **IP 级 + 跨域生效**：`seal` 被封后，`www` / `lms` / `eps` / `lst` 等**所有** sheincorp / dotfashion 域同时返回同一张拦截页 |
| **阈值估计** | 单主机 **15~30 次**异常路径请求量级（259 条正常探活 + 60 次 actuator/nginx 探测**都没触发**） |
| 路径级规则 | `/metrics`、`/swagger` 直接 403（WAF 带敏感路径规则库） |
| 关键词级规则 | `/etc/passwd`、`file://` 等敏感词出现在 body 即拦 |
| **真实浏览器是否有效** | ✅ **有效**。改「真实 Chrome + 页面内 fetch + 随机 6~12s 间隔 + 跨主机再等 5~6s」后，**30 个请求分布 6 个主机 → 零封禁** |
| 体积绕过 / CT 互换 / RFC2231 | 未测且不适用 —— 本场景的拦截点在 **path 与行为**，不在 body 解析层 |

### 14.4 ★★ 最有价值的一条结论

**对这类 WAF，"过"的关键不是改 payload，而是降低「请求特征 + 速率」。**

同一个目标、同一批路径：
- Python 裸打 **16 次** → IP **全域拉黑**
- 真实浏览器 + 低频 + 随机间隔 **30 次** → **零触发**

⇒ **它判断"像不像人在用浏览器"的优先级，高于"内容里有什么词"。**
落地工具：`tools/cdp/cdp_slow.py`（页面内 fetch + 随机间隔 + 拦截页自动熔断）。

### 14.5 纪律

1. **被封后不要在同一个 IP 上继续** —— 全域生效，接着打只会拉长封禁，且所有结论都不可信。
2. **哨兵法**（同 §13.2）：始终留一个**已知正常的请求**当探针，它被拦就说明环境已脏，**立刻停手**。
3. **主动告知用户**：被封要把拦截页里的 `EVENT ID` 一并报给用户，而不是当成"不可访问"糊过去。
4. **★★ 破坏性验证会烧掉你出口 IP 的可信度（2026-09-17 亲例）**：
   同一目标上 ~40 个**普通探测请求**（23:0x–23:20）完全没事；
   紧接着做了**破坏性验证（渲染进程内存耗尽 → 多次 OOM 崩溃 `[page-crash]`）**，
   十余分钟后再打**哨兵**（已知正常路径）时，已经是 **403 + 2662 字节拦截页**。
   ⇒ **触发封禁的是"让服务端出现异常"这件事本身**（进程崩溃是很显眼的异常事件），**而不是请求数量**。
   **纪律**：
   ① 破坏性验证**做完立刻打哨兵复检**，别等到下一轮才发现环境已脏；
   ② 手头**常备备用出口 IP**（破坏性验证前就要准备好）；
   ③ 破坏性动作压到**最小必要次数** —— 本次三级 OOM 里，前两级（512MB / 1.5GB）已足以判断隔离强度，
   **第三级（3GB，唯一把它打崩的那级）其实可以不做**。
5. **判别封禁要跨域验证**：GSRM 的封禁是**跨域生效**的。哨兵被拦后，
   再取一个**完全不同主机**的目标（亲例 `ulp-test01.sheincorp.cn`）看是否同一张拦截页 ——
   同为 2662 字节页 ⇒ 确认是 IP 级封禁而非单站故障。

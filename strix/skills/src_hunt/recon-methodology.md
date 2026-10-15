---
name: "recon-methodology"
description: "recon-and-methodology"
---

# recon-and-methodology

> **测绘节奏只认** `dig-scope` §1.0.1 / §2.1：只搜**当前这一个**种子；本种子剩余活面没挖完禁止新搜。认到短表形态只打当前站，禁止拿 Morph 去全网 FOFA。优质根域只回灌，本种子挖完才搜。
>
> **全量 nuclei 不当进度。** nuclei 只在需要已知 CVE / 暴露面（actuator、swagger、已知中间件）时辅助；禁止把「全量模板扫一遍」当本站矩阵。
>
> 调搜用 MCP `fofa`（`fofa__get_alerts`），不要自己 curl。Key 在 `~/.workbuddy/mcp.json` `[mcp_servers.fofa.env]`：主号 → backup → backup2，`fofa.py` 遇 429/820041 自动切。限流闸认 `dig-scope` §2.1.4。**禁止**把 email / key 写进本文件或对话。

### FOFA 最短语法（备忘，不是开场）

```
qbase64：查询语句 UTF-8 再 Base64
fields：host,ip,port,title,server
size：先小后翻；本种子结果可翻页，不是换种子

domain="target.com"
header="application/json"
body="actuator"
port="8080"
server="nginx" && domain="target.com"
cert.subject="品牌"
icon_hash="xxx"
status_code="200"
组合 && ；排除 !=
```

Quake / 凤鸟只补**当前种子**缺口，不当开场必跑。语法对照与 ROI 过滤见下文各节；过滤仍服从 `dig-scope` 去废 / 去非存活 / 股权闸。

# Recon and Methodology


## 1. RECON HIERARCHY

```
Target Selection
└── Scope Definition (in-scope assets)
    └── Asset Discovery (subdomains, IPs, domains)
        └── Tech Fingerprinting (what's running)
            └── Endpoint Discovery (attack surface)
                └── Vulnerability Testing (per vulnerability type)
```

---

## 2. SUBDOMAIN ENUMERATION (CRITICAL FIRST STEP)

### Passive (no DNS queries to target)
```bash
# Subfinder (aggregates multiple sources):
subfinder -d target.com -o subdomains.txt

# Amass passive:
amass enum -passive -d target.com

# Certsh (certificate transparency):
curl -s "https://crt.sh/?q=%.target.com&output=json" | jq -r '.[].name_value' | sort -u

# SecurityTrails API, Shodan:
# Web: https://securitytrails.com/list/apex_domain/target.com
```

### Active (DNS brute force + resolution)
```bash
# Massdns + wordlist:
massdns -r /path/to/resolvers.txt -t A -o S -w output.txt \
  <(cat wordlist.txt | sed 's/$/.target.com/')

# ffuf for subdomain brute:
ffuf -w subdomains-wordlist.txt -u https://FUZZ.target.com \
  -mc 200,301,302,403 -H "Host: FUZZ.target.com"

# DNSx for bulk resolution:
cat subdomains.txt | dnsx -a -resp -o resolved.txt

# Recommended wordlist: SecLists/Discovery/DNS/
```

### Virtual Host Discovery
```bash
# ffuf vhost mode:
ffuf -w wordlist.txt -u https://target.com \
  -H "Host: FUZZ.target.com" -mc 200,301,403

# gobuster vhost:
gobuster vhost -u https://target.com -w wordlist.txt
```

---

## 3. SERVICE AND PORT DISCOVERY

```bash
# Fast port scan (common ports):
nmap -T4 -F target.com -oN ports.txt

# Comprehensive scan on resolved subdomains:
cat resolved_ips.txt | nmap -iL - --open -p 80,443,8080,8443,8888,3000,5000 -oG scan.txt

# httpx for HTTP probing:
cat subdomains.txt | httpx -title -tech-detect -status-code -o live_hosts.txt

# masscan for speed on large IP ranges:
masscan -p 80,443,8080,8443 10.0.0.0/8 --rate=1000
```

---

## 4. WEB TECHNOLOGY FINGERPRINTING

```bash
# Wappalyzer (browser extension) or:
whatweb https://target.com

# httpx with tech detection:
httpx -u https://target.com -tech-detect

# Check headers manually:
curl -sI https://target.com | grep -i "server\|x-powered-by\|x-generator\|cf-ray"

# Fingerprint from:
- Server header: nginx/1.18, Apache/2.4, IIS/10.0
- X-Powered-By: PHP/7.4, ASP.NET
- Cookies: PHPSESSID (PHP), JSESSIONID (Java), _rails_session (Rails)
- HTML comments: <!-- Drupal 9 -->
- Meta generator: <meta name="generator" content="WordPress 6.2">
- JS framework files: /static/js/angular.min.js
```

---

## 5. ENDPOINT DISCOVERY

### Directory Brute Force
```bash
# ffuf (fastest):
ffuf -u https://target.com/FUZZ -w /usr/share/seclists/Discovery/Web-Content/raft-medium-files.txt \
  -mc 200,301,302,403 -t 50 -o dirs.txt

# Gobuster:
gobuster dir -u https://target.com -w wordlist.txt -x php,html,js,json

# feroxbuster (recursive):
feroxbuster -u https://target.com -w wordlist.txt -x php,html,txt -r
```

### Parameter Discovery
```bash
# Arjun (hidden parameter finder):
arjun -u https://target.com/api/endpoint

# x8:
x8 -u https://target.com/api/endpoint -w params-wordlist.txt
```

### JavaScript Source Mining
```bash
# Extract endpoints from JS files:
gau target.com | grep '\.js$' | httpx -mc 200 | xargs -I{} curl -s {} | \
  grep -oE '"/[a-zA-Z0-9/_-]+"' | sort -u

# LinkFinder:
python3 linkfinder.py -i https://target.com -d -o output.html

# GetAllURLs (gau):
gau target.com | sort -u > all_urls.txt

# Wayback URLs:
waybackurls target.com | sort -u > wayback_urls.txt
```

### API Endpoint Discovery
```bash
# Common API paths:
ffuf -u https://target.com/FUZZ -w /SecLists/Discovery/Web-Content/api/api-endpoints.txt

# Swagger/OpenAPI:
test: /swagger.json /api-docs /openapi.json /v2/api-docs /.well-known/ /docs/

# GraphQL:
test: /graphql /gql /v1/graphql /api/graphql
```

---

## 6. SOURCE CODE RECON

### GitHub / GitLab Exposure
```bash
# trufflehog (secret scanner in git history):
trufflehog git https://github.com/target-org/target-repo

# gitleaks:
gitleaks detect --source /path/to/cloned/repo

# Manual GitHub search:
# site:github.com "target.com" "api_key" OR "secret" OR "password"
# site:github.com "target.com" ".env" OR "config.php" OR "db_password"

# GitHub dorks:
# "target.com" extension:env
# "target.com" filename:*.config password
# org:target-org secret OR password OR apikey
```

### Exposed Environment Files
```
# Check common paths:
https://target.com/.env
https://target.com/.git/config
https://target.com/config.json
https://target.com/config.yaml
https://target.com/credentials.json
https://target.com/secrets.json
https://target.com/wp-config.php
https://target.com/backup.sql
https://target.com/backup.zip
```

---

## 7. ZSEANO'S TESTING METHODOLOGY

> **节奏不听本节。** 自由跳 / 一种子 / 力气先砸哪认 `dig-scope` + `src-value` §1.1。本节只当：参数怎么想、错误页/旧版本/移动端 API 别漏。命令和思路仍用。

### Core Philosophy
1. **Go deep on one program** rather than spread across many — learn the application thoroughly
2. **Build a profile of the company** — tech stack, developers, processes
3. **Look where others don't** — check error pages, admin paths, old versions, mobile API
4. **Follow the filter** — if input is filtered somewhere, that functionality exists and may be bypassed

### Testing Sequence (One Page / Feature)
```
For each input point:
1. Non-malicious HTML tags (<h2>, <img>) → are they reflected?
2. Incomplete tags → what happens? (<iframe src=//evil.com )
3. Encoding tests → %0d, %0a, %09, <%00
4. Observe the OUTPUT too (not just response) — where does your input appear?
5. Test same input in ALL similarly-structured pages (shared code → shared vuln)
6. Check if the same parameter exists in mobile/API endpoint (less protected)
```

### Parameter Insights
```
- Each parameter tells a story: "what does this do server-side?"
- Filename → OS interaction → Path Traversal / CMDi
- URL/location → HTTP fetch → SSRF
- Template/HTML parameter → render function → SSTI
- XML field → parser → XXE
- SQL filter → query → SQLi
- User-content → storage → Stored XSS
```

---

## 8. BUG BOUNTY PROGRAM TRIAGE (WHERE TO SPEND TIME)

> **节奏不听本节。** 自由跳种子/换站认 `dig-scope`；力气先砸哪认 `src-value` §1.1。下面 Priority 不是第二套测绘，也不是 SRC 定级。命令和参数思路仍用。

### High-Value Target Selection
```
✓ Programs with large scope (*.target.com)
✓ Programs that pay for P2/P3 (not just RCE)
✓ Programs with recent tech changes (migrations = new bugs)
✓ Programs with active development (new features = new attack surface)
× Avoid: frozen/old codebases with well-known CVEs (already claimed)
× Avoid: strict programs with narrow scope (less surface)
```

### High-Value Feature Focus (by bug probability)
```
Priority 1: Authentication, password reset, 2FA → account takeover
Priority 2: File upload, profile edit, API endpoints → stored XSS, IDOR
Priority 3: Admin panels, user management → BFLA, privilege escalation
Priority 4: Payment flows, subscription → business logic
Priority 5: Import/export, template rendering → XXE, SSTI
```

---

## 9. NUCLEI TEMPLATES (AUTOMATED SCANNING)

全量模板扫一遍不当进度。只在已知 CVE / 暴露面需要时收窄模板。

```bash
# 收窄：已知 CVE / 暴露面，不要当开场全量
nuclei -u https://target.com -t cves/ -severity critical,high
nuclei -u https://target.com -t exposures/
nuclei -u https://target.com -t misconfiguration/

# On subdomain list:
cat subdomains.txt | nuclei -t exposures/ -t misconfiguration/ -o exposed.txt
```

---

## 10. COMMON MISCONFIGURATIONS (QUICK WINS)

```
□ CORS: SRC 永久跳过（不挖不写；见 cors-vuln-report-priority）— 勿当 quick win
□ S3 bucket public: curl https://target.s3.amazonaws.com/
□ Directory listing: response contains "Index of /"
□ .git exposed: curl https://target.com/.git/config
□ .env exposed: curl https://target.com/.env
□ Debug mode: stack traces in production (source code exposure)
□ Default credentials: admin:admin, admin:password on admin panels
□ phpinfo.php: curl https://target.com/phpinfo.php
□ Backup files: config.bak, database.sql.gz, app.zip
□ GraphQL introspection enabled: POST /graphql {"query":"{__schema{types{name}}}"}
□ Admin panels: /admin /manager /console /phpmyadmin /wp-admin
```

---

## 11. QUICK REFERENCE TOOLS

| Category | Tool |
|---|---|
| Subdomain enum | subfinder, amass, massdns |
| Port scan | nmap, masscan |
| HTTP probe | httpx |
| Dir brute | ffuf, feroxbuster, gobuster |
| JS mining | LinkFinder, gau, waybackurls |
| Secret scan | trufflehog, gitleaks |
| Parameter fuzz | arjun, x8 |
| Vuln scan | nuclei |
| Proxy/intercept | Burp Suite Pro |
| JWT attacks | jwt_tool |
| SQLi | sqlmap |
| XSS | dalfox, XSStrike |
| SSRF | SSRFmap, Gopherus |

---

## 12. JAVA MIDDLEWARE FINGERPRINT MATRIX

| Middleware | Detection Path | Key Indicators |
|---|---|---|
| Apache Tomcat | `/manager/html`, `/manager/status` | Default creds: `tomcat:tomcat`, `admin:admin` |
| JBoss / WildFly | `/jmx-console/`, `/web-console/` | JMX MBean access, WAR deployment |
| WebLogic | `/console/`, `/wls-wsat/` | T3 protocol on 7001/7002, IIOP |
| Spring Boot Actuator | `/actuator/`, `/actuator/env`, `/actuator/heapdump` | JSON endpoint listing, heap dump contains secrets |
| Spring Boot (alt paths) | `/actuator/jolokia`, `/actuator/gateway/routes` | Jolokia JMX bridge, Gateway route injection |
| Jenkins | `/script`, `/manage` | Groovy console, API token in cookie |
| GlassFish | `/common/`, `/theme/` | Admin on 4848, default empty password |
| Jetty | `/jolokia/` | JMX access |
| Resin | `/resin-admin/` | Admin panel |

### Spring Boot Actuator Exploitation Priority

```
/actuator/env          → Leak environment variables (DB creds, API keys)
/actuator/heapdump     → Download JVM heap → search for passwords in memory
/actuator/jolokia      → JMX → possible RCE via MBean manipulation
/actuator/gateway/routes → Spring Cloud Gateway → SpEL injection (CVE-2022-22947)
/actuator/configprops  → All configuration properties
/actuator/mappings     → All URL mappings (hidden endpoints)
/actuator/beans        → All Spring beans
/actuator/shutdown     → POST to shutdown application (DoS)
```

---

## 13. INFORMATION LEAK DETECTION CHECKLIST

### Version Control & Backup Leaks

```
/.git/HEAD                    → Git repository exposed
/.svn/entries                 → SVN metadata
/.svn/wc.db                   → SVN SQLite database
/.hg/requires                 → Mercurial
/.bzr/README                  → Bazaar
/.DS_Store                    → macOS directory listing
```

### Backup File Patterns

```
/backup.zip    /backup.tar.gz    /backup.sql
/wwwroot.rar   /www.zip          /web.zip
/db.sql        /database.sql     /dump.sql
/config.php.bak    /config.php~    /config.php.swp
/.config.php.swp   /wp-config.php.bak
/.env          /.env.bak         /.env.production
```

### API Documentation & Debug

```
/swagger-ui.html              → Swagger/OpenAPI
/swagger-ui/                  → Swagger UI
/api-docs                     → API documentation
/graphql                      → GraphQL playground
/graphiql                     → GraphQL IDE
/debug/                       → Debug endpoints
/phpinfo.php                  → PHP configuration
/server-status                → Apache status
/server-info                  → Apache info
/nginx_status                 → Nginx status
```

### Cloud & Infrastructure

```
/.aws/credentials             → AWS credentials
/.docker/config.json          → Docker registry auth
/robots.txt                   → Disallowed paths (hint list)
/sitemap.xml                  → Full URL listing
/crossdomain.xml              → Flash cross-domain policy
/.well-known/                 → Various well-known URIs
```

---

## 14. 锁面清单的「探活 + 三分类」工作流（2026-09-18 乐信实证）

> 场景：用户丢来一份**固定域名清单**（锁面），要求「探活 + 分类」。交付物是**资产分类表**，不是漏洞报告。
> 参考实现：`C:/Users/86182/Desktop/乐信_SRC挖洞/乐信_dig/`（`probe.py` / `login_probe.py` / `make_table.py` / `ct/`）。

### 14.1 三步走

| 步 | 做什么 | 产出 |
|---|---|---|
| 1 | **探活**：每个 host 分别 `https` / `http` 单发一次；记 DNS、状态码、跳转链（自己实现 `HTTPRedirectHandler` 记录）、Server/Content-Type、title、body 长度；body 原样落 `raw/<host>.<scheme>.html` | `probe_raw*.json` + `raw/` |
| 2 | **分类**：**必须用真实浏览器渲染**（`tools/cdp/cdp_batch.py`），抽渲染后 URL / 标题 / 输入框 placeholder / 密码框数 / 按钮文案 / 相关 href | `cdp_batch_out*.json` |
| 3 | 汇总成全表（host / 分类 / 存活 / 状态码 / 标题 / Server / 体积 / 说明） | `资产/资产总表.tsv` |

脚本要支持 `probe.py <hosts文件> <输出后缀>` 多轮跑 —— 扩面会发现新 host，需要增量第二轮、第三轮。

### 14.2 ★ 最大的坑：**SPA 站点的「能不能注册」绝不能用路径探测判**

对 SPA（Vue/Angular/React）打 `/login`、`/register`、`/signup`、`/api/` **全部返回同一个外壳页，
状态码全 200、体积完全相同**（乐信实测：`passport.fenqile.com` 所有路径都返 29796 字节的同一份 shell；
`cia/panshi/spv/m-crm.dszc-amc.com` 同理）。

⇒ 路径探测对 SPA **零信息量**。判定「登录页长什么样 / 有没有注册入口」**唯一可靠依据是浏览器渲染后的
按钮文案与 URL**（`cdp_batch.py` 的 `regBtns` / `regHrefs` / `href` 字段）。
渲染与路径探测的关系：**路径探测只用来区分「真 404 服务」与「SPA 兜底」**，分类结论一律以渲染为准。

### 14.3 三分类的判定口径（避免主观）

| 分类 | 硬判据 |
|---|---|
| **A 免登录可访问** | 无登录态打开即有实质内容：官网/公开 API（无参就吐业务 JSON）/招聘前台/开放平台首页/CDN 存活探针 |
| **B 可注册** | 存在**自助注册入口**。两类都算：① 显式按钮「注册 / 开户 / 注册成为开发者 / 资金方注册」；② **手机号 + 短信验证码「首登即建号」**的自助开户（无独立注册页也要归 B，别漏） |
| **C 仅登录、不支持注册** | 有登录页但无任何自助注册入口（企业 SSO / 账号由 HR·IT 发放 / 只有「重置密码」） |
| D 其他存活 | 中间件默认页（`Welcome to tengine!`）、404 页、空响应、纯 CDN 探针 → 单列，别塞进 A |
| N 无解析 | NXDOMAIN。**必须用公共 DNS 交叉核验**（本地 DNS 常有污染/拦截），否则会把证书历史遗留域当活资产 |

### 14.4 探活结果的解读纪律

- **`502 upstream connect failed: 不知道这样的主机` 是代理侧报的 NXDOMAIN，不是目标返回的** ⇒ 判「不存活」，
  别当活资产写进表（亲例：一批 `*.lexin.com` 子域如此）。
- **TLS 握手失败 ≠ 站点死**：`ir.lexin.com` 对 Python urllib 直接 `TLSV1_ALERT_INTERNAL_ERROR`，
  但 `curl` 与浏览器正常、`http://` 200 ⇒ peer 卡 ClientHello（指纹/协议版本），换 curl 或降级 http 重测。
- **DNS 解析有 A 记录但连接超时 ⇒ 记「存活但不可达」**（如 VPN 网关），不是「无解析」。
- **302 到另一个登录域 = 同一登录壳**：把这类 host 全归到同一「登录枢纽」下，
  后续按 §4.1.2「同闸」处理（代表站做完，sibling 一眼差分即可）。

### 14.5 扩面：证书日志对这类站的收益可能极低

```bash
# ★ 脚本里 %25 要写成 %%（否则被 Python % 格式化吃掉）；curl 里直接写 %25
curl -s "https://crt.sh/?q=%25.<域>&output=json" -o ct/<域>.json
```

实测 `lexin.com` 11 条 / `fenqile.com` 9 条 / `dszc-amc.com` **1 条** / `rhinocloud.com.cn` **1 条** ——
中文金融/消金业务域**大量使用通配符证书且未入 CT**，crt.sh 基本捞不到业务子域。

⇒ 这类目标的扩面应优先走：
1. **进站 JS 里的 `dns-prefetch` / `preconnect` / `baseURL`**（乐信亲例：一个小程序 H5 的 `<link rel="dns-prefetch">`
   一次带出 10 个 CDN 域）；
2. **SSO 跳转链的 `?url=` 参数解码**（亲例：`passport.lexincloud.com/?url=...` 层层嵌套 base64/URL 编码，
   解码后带出 `oa.fenqile.com`、`leco.oa.fenqile.com`、`openmoa.oa.fenqile.com` 三个内部域）；
3. 报错页 / 页脚 / 备案号反查。

### 14.6 请求纪律（红线）

- 每 host 每协议**单发**；三批探活合计约 190 请求 / 70 host，单主机累计 ≤ 10 次 ⇒ 不触 DoS 红线。
- 一律 GET、无 payload、无并发压测；不碰发短信/验证码/登录试错。
- 渲染用 `cdp_batch.py`（真实浏览器，比裸打更「像人」），`--wait 8` 给重 SPA 足够时间。

### 14.7 ★★ 三分类的六个判定陷阱（2026-09-21 理想 533 host 实证）

一、**第三方 IdP 的「注册」不算本系统可注册**。亲例 `bpm.lixiangoa.com` 渲染出
「还没有账号？立即注册」，看着像 B 类 —— 但 href 是 `accounts.feishu.cn/...`，
**注册飞书 ≠ 能进理想 BPM**（还要企业内部授权）。⇒ 过滤 `IDP_PAT`：
`feishu|lark|dingtalk|alibaba|wechat|qq|tencent|okta|auth0|microsoft|google`，
命中即归 **C**（子类「仅登录·第三方IdP」）。理想这类系统占比很高（21/78）。

二、**页脚的「注册协议 / 隐私政策」不是注册入口**。亲例 `www.lixiang.com` 的
`hrefs` 里含 `/agreement/register.html`，正则一命中就误判成 B。
⇒ 过滤 `NOISE_PAT`：`协议|政策|条款|声明|agreement|privacy|terms|policy|beian|备案`。
同时排除 `beian.gov.cn` 的备案链接（几乎所有国内站的页脚都有）。

三、**渲染不出内容时绝不能判「免登录」**。亲例 `carservice`/`sec-ys-cmd`/`sso.chehejia.com`
在 CDP 里 `textLen=0`（SPA 要登录态或 JS 失败）⇒ 若按「HTTP 200 且有 body」兜底就全判 A，**错**。
正确：`textLen<30` 时不判 A，按 title 保守归类并在「判定依据」里写明
「渲染未出内容，业务系统保守归入，建议登录态复核」——**留痕可追溯**比强行给结论重要。

四、**「整页被顶到登录面」才叫仅登录，导航栏有个登录链接不算**。
判据用 `urlparse(href)` 而非正则扫全 URL：
`netloc` 含 login/sso/oauth（如 `account.lixiang.com`）**或** `path` 形如 `/login`（如 `editor.lixiang.com/login`）
→ C；`netloc==host 且 path=='/'`（如 `www.lixiang.com/`）→ 不算。
亲例：`www.lixiang.com` 因导航栏有「登录」被判 C（错），改判据后回到 A（官网 1455 字）。

五、**`502 upstream connect failed: … (os error 10061)` 是本机代理报的，不是目标返回的**。
本机 bash 注入了 `http_proxy`，代理连不上上游就吐这句中文错误 ⇒ 与「目标 502」完全不同。
判法：同一 host **代理 + 直连各打一次**。亲例 `accounting.chehejia.com` 代理 502 / 直连 timeout
⇒ 两边都不通才是真结论；`123.chehejia.com` 两边都 200 ⇒ 一致。
（承 §14.4「`502 … 不知道这样的主机` 是代理侧 NXDOMAIN」的同族坑。）

六、**公网 DNS 解析到内网 IP ≠ 本地 DNS 环境问题**，必须用公共 DNS 交叉验证。
亲例：40 个理想内部系统（`oa`/`wiki`/`gitlab`/`nexus`/`sec`/`scan`/`db`/`gerrit`…）返回
`192.168.x`/`172.x`/`10.x`。用 `nslookup <host> 223.5.5.5` 复验 —— **同样返回内网地址**
⇒ 是目标公网权威 DNS 真的配了 RFC1918 A 记录 ⇒ **内网拓扑泄漏**（主机名语义 + IP 段分布），
单独列 **I 类**，不要混进「无解析」。这一条给钓鱼/横向提供了精确地图，是可直接入报告的低危。

七、★★★ **泛解析域（`*.xxx`）：DNS 有解析 ≠ 真实资产；「默认站标记词」必须用「只属于兜底页的路径串」，不能用实体名**（2026-09-26 cdcas 实证）。
亲例：`*.cdcas.edu.cn` **任意子域**（含 `zzz-not-exist-xyz.`）都解析到 `111.231.213.107`，
返回站群默认站「云南城市建设职业学院-官网」，唯一可靠指纹是 `www.yncjxy.com/inc/*.js`（模板路径）。
- ⇒ 该域上做 DNS 字典扩面**零信息量**（80 词跑完零新增）；扩面只能靠**渲染后内容差分**（title ≠ 默认站才算真站）。
- ⇒ 三分类里另列 **X 泛解析默认站**，别混进 A（否则会把别人的站当成本校资产）。
- ★★ **标记词选错的代价（亲例）**：我最初用 `("yncjxy.com", "云南城市建设职业学院")` 做兜底标记，
  结果 **`zbpt.cdcas.com`（数字化招采平台）被误判成默认站** —— 因为它的**招标公告正文里**真的出现了
  「云南城市建设职业学院校园照明设施采购及安装预审公告」。
  ⇒ **兜底页标记必须是「只可能出现在兜底页的路径/资源串」**（`yncjxy.com/inc/`），
  **边界条件再加「body 长度 < 4KB」**。同理：**出现在业务正文里的实体名（校名/公司名）永远不能当指纹**。
  这一条与 §14.7 二的「页脚注册协议」、`指纹库` 章「实体名当指纹」是同一族假阳性。

八、★★ **CDP 补渲染：IP 直连 / 自签证书站点会 `eval empty`，需第二个 Chrome 带 `--ignore-certificate-errors`**（2026-09-26 cdcas）。
`tools/cdp/cdp.py` 启动 Chrome 时**不带** `--ignore-certificate-errors` ⇒ 形如
`https://<IP>:9443/`、SNI 不匹配的站点会停在证书拦截页，`cdp_batch.py` 记 `error:"eval empty"`（**不是站点死**）。
对策（一条命令内完成）：自己起一个 Chrome 实例再指过去 ——
```bash
"$PY312" -c "import subprocess;subprocess.Popen([r'C:/Program Files/Google/Chrome/Application/chrome.exe',
 '--remote-debugging-port=9555','--user-data-dir=<新profile>','--no-first-run','--no-proxy-server',
 '--ignore-certificate-errors','--allow-running-insecure-content','https://me/'],creationflags=0x8|0x200)"
CDP_PORT=9555 "$PY312" cdp_batch.py urls2.json --out out2.json --wait 7
```
亲例收益：补渲染后才拿到 **雷池(SafeLine) WAF 个人版** 登录页、**小北校友**「注册」按钮（B 类判据）、
腾讯企业邮的「注册新企业」（IdP 噪声）—— 不补这批，三分类会漏 3 条且 B 类少 1 条。

九、★★ **`urllib.request.build_opener` 会自动补 `ProxyHandler()`（读 `http_proxy` 环境变量）** ⇒
想「直连」必须显式写 `build_opener(ProxyHandler({}), HTTPSHandler(context=ctx))`；
否则所谓「直连」仍在走代理，**与目标真实可达性无关**（表现为 `Tunnel connection failed: 502 Bad Gateway`
一直存在，容易误判成目标 502）。承 §14.7 五、§14.4。

十、★★ **按 host 聚合渲染结果时，必须剔除「显式非默认端口」的 URL**。
`urlparse(u).hostname` 会把 `http://www.cdcas.com:11701/cgi-bin/luci/`（iStoreOS 路由器）与
`https://www.cdcas.com/`（学校官网）并进同一个 host 桶 ⇒ 高 textLen 的那条覆盖掉官网记录，
分类直接错。做法：`if pr.port and pr.port not in (80,443): continue`，非默认端口一律单列成「端口行」。

**附：两个新增分类**
- **E 内网/VPN 限制**：公网可达但页面明说「请连接公司内部网络或VPN后访问」
  （亲例 `linote.lixiang.com`、`process.chehejia.com`）。特征词：`连接理想汽车内网|连接公司内部网络|外部网络浏览|内网或VPN`。
  ★ 注意读 body 别只读前 4KB —— 亲例 `linote` 的关键句在 4000 字节之后，只读 4KB 会漏判。
  ★ 补充判据（2026-09-26 cdcas）：**页面资源明文指向 RFC1918 地址**（`wx.cdcas.com` 的
    `<link href="http://172.22.33.180:80/css/gao/gao_login.css">`）⇒ 同样归 E，且顺带是**内网 IP 泄漏**（I 类）。

- **D-IP白名单**：`{"message":"Your IP address is not allowed"}`（亲例 `jira.it.chehejia.com`）——
  服务端起效的来源限制，不是站点死。

**附：僵尸解析 / 潜在子域接管**（理想 93 个 host 共指 `180.76.97.127`）
判法三步：① 随机子域 `NXDOMAIN` ⇒ **排除泛解析**，这 93 条是逐条配的 A 记录；
② 该 IP 的 443/80/22 全部 **TimeoutError（drop，非 RST）**，而对照 IP 立即 OPEN ⇒ 不是网络问题；
③ 结论只能写「DNS 仍指向一个无服务的 IP，**若该 IP 已释放则存在接管风险**，归属**未验证**」——
**不要**写成「存在子域接管漏洞」。
另：24 个超时域名为邮件/VPN 类（`smtp`/`imap`/`pop3` 只开 25/143/110、`sslvpn*`、`feishu-vpn`）⇒ 正常，别当异常。

**附：crt.sh 对这类站的收益（与 §14.5 的结论互补）**
`chehejia.com` **1105 条 → 79 个主机名**、`lixiangoa.com` **1406 条 → 58 个**、`lixiang.com` 399 条 → 34 个。
理想**不是** §14.5 里乐信那种「通配符证书未入 CT」的情况 —— **三个根域都大量入 CT**，
新增 136 个主机名（k8s 集群、`gitlab.`/`gerrit.`/`nexus.` 工具链、`supplier.`/`learning.`/`cae.` 业务线）。
⇒ 所以 §14.5 那句「中文金融域收益极低」**不能套用到所有中文企业域**，**每站都要实测**，
不要因为读过那条就跳过 crt.sh。`crt.sh` 偶发 502（代理侧）⇒ 重试 + 直连兜底即可，别判死。

---

### 14.8 ★★★ 交付「资产 IP」前必做 **CDN 核验**（2026-09-26 cdcas 实证）

> 触发：任务要「把这个学校的 IP 给我」。**A 记录 ≠ 源站** —— 直接报 A 记录 IP 可能是 CDN/网关边缘。
> 四条判据（全做完再下结论，成本约 1 分钟）：

| # | 判据 | 命令要点 | 读法 |
|---|---|---|---|
| 1 | **CNAME 链** | `nslookup -type=CNAME <host> 223.5.5.5` 取 `canonical name =` | 指向 `*.cdn.dnsv1.com`/`*.wscdns.com`/`*.kunlungr.com`/`*.akamai*` 等 ⇒ **边缘**；无 CNAME ⇒ 更像直连 |
| 2 | **CDN 特征响应头** | 拉全响应头 grep `X-Cache`/`Via`/`Age`/`X-Served-By`/`X-NWS-LOG-UUID`/`X-Swift` | 命中 = 过代理层；**全空 = 无 CDN**。⚠️ 正则别用宽泛的 `cache/age/via` —— 亲例 `Access-Control-Max-Age`、`Content-Language` 都会命中 `age:` 子串，是**假阳性**，必须回原文核对 |
| 3 | **多公共 DNS 的 A 一致性** | 同一 host 问 `223.5.5.5` / `1.1.1.1` / `8.8.8.8` | 三家**完全一致** ⇒ 单一 A、无按解析器/地理轮询；**同一域名跨 DNS 拿到不同 IP** ⇒ 疑 LB/CDN |
| 4 | **TLS 证书归属**（最强） | 取 peer cert 的 `SubjectAlternativeName` | 多个**不同 IP** 上装的都是**同一张「客户自己的泛域名证书」**（`*.cdcas.com`）⇒ **自建服务器集群**；CDN 边缘是按域签发的边缘证书，形态不同。★ 还能反向用：`dm.cdcas.com` 的证书 SAN 是 `*.yinghuaonline.com` ⇒ **这站根本不由本校运维** |
| 5 | **TCP 端口指纹**（区分「真主机」vs「纯转发 VIP」） | 对 IP 做纯 `connect()`（**不发任何数据**）探 22/3389/3306/8080 | 开**管理/服务端口**（22 SSH / 3389 RDP / 3306 MySQL）⇒ **是真主机**；**只开 80/443** ⇒ 更可能是网关/负载 VIP（注意：云主机安全组只放 80/443 时也会这样，**只作辅证不作定论**） |

辅证：**PTR 反解**（CDN 节点一般有 `*.cdn.dnsv1.com` 一类反解，纯云主机常无）；**IP 段性质**
（云厂商 CVM/轻量段 vs CDN 节点段；IDC/专线段如联通 `101.207.126.0/24` ≈ 自建托管）。

★ **必须剔除 / 标注的三类**（亲例全部踩到）：
- **DNSPod 免费 URL 转发**：`js`/`jw`/`tsjq.cdcas.com` CNAME → `dnspod-free.beian.mydnspod.net`，
  IP 是 DNSPod 的转发节点，**不是客户资产**（且跨 DNS 轮询两个 IP）。
- **托管邮箱 / SaaS**：`mail.cdcas.edu.cn` CNAME → `tp.exmail.qq.com`（腾讯企业邮），IP 是厂商集群。
- **`Server: stgw` = 腾讯云七层网关/负载均衡**：看到的 IP 是**网关 VIP，后端不可见**
  ⇒ 只能写「网关可达」，**IP ≠ 源站**。同域名的 **80 端口走 stgw、443 直连 Apache** 是常态，**端口结论必须分 80/443**。
- ★★ **同一 IP 上「80 与 443 是两个东西」要用原始报文确认，别按 Server 头一刀切**：
  亲例 `111.231.213.107` —— 443 = Apache + 学校自有证书 + HZCMS 应用指纹（**源站**）；
  80 = **固定 189 字节、与 Host 无关**的 stgw 503 页，且响应头带**他方 CORS 配置**
  `Access-Control-Allow-Origin: https://site.zjzw.cn` ⇒ **共享网关的兜底页 + 配置残留**。
  ⇒ 结论要写成「**该 IP 的 443 是源站、80 走网关**」，而不是笼统判「这 IP 是不是源站」。
  （判法：同 IP/同端口换 **已知 Host / 完全编造的 Host** 各发一发，**两者逐字节相同 = 该端口不分 Host = 不是应用入口**。）

★ **口径**：以上是**公开指纹推断**，不是控制台级证明。报告里要写明「依据 + 边界」，
需要 100% 确证时应做**多地域出口探测**或请运营方确认。**别把「推断」写成「确认」。**

---

## 15. ★★ SPA 前端 chunk 大面积「被兜底成 HTML」时：回 index.html 找真实 CDN 域（2026-09-18 乐信 open.fenqile.com 实证）

### 15.1 症状与误判

抓包看到浏览器请求了一堆 `/static/js/34.*.js` … `/static/js/83.*.js`，**全部返回
`200 text/html`、且长度与首页外壳逐字节相同（7183B）**，`Content-Type: text/html`。

**第一反应容易误判成**「前端构建产物版本不一致 / 部署残留 / nginx 配置错」—— 我第一轮就是这么写的。
**实际原因往往更简单：这些 chunk 根本不该从这个域取。**

### 15.2 正确做法（一步定位）

**回到 `index.html`（或任意 SPA 外壳页）读 `<script src>` 的绝对地址**：

```bash
# 从抓包/直接请求里拿外壳页
grep -oE '(src|href)="[^"]+\.(js|css)"' index.html
```

乐信亲例，外壳页里写的是：

```html
<script src="https://cresauth.fenqile.cn/work-loan-open/static/js/8.9efc4b2c.js"></script>
<script src="https://cresauth.fenqile.cn/work-loan-open/static/js/main.18788bcb.js"></script>
```

**不是** `open.fenqile.com/static/js/...`，而是 **`cresauth.fenqile.cn/work-loan-open/static/js/...`**。
代入后 **83 个 chunk 全部 200 且都是真 JS（6.5MB），零失败**。

> **CDN 与门户不同域是常态**（`static.` / `cres*.` / `cresauth*.` / `*.cdn.`）。
> 浏览器会因为 webpack `publicPath` 配成相对路径而请求到门户域 → 被 SPA catch-all 吞掉。

### 15.3 拿到 chunk 后的实测收益（乐信亲例）

| 项 | 只有 main.js | 拿到 83 chunk 后 |
|---|---|---|
| 接口清单 | 27 个 | **108 个 `/route*` + 15 个 channel/field** |
| 后台路由 | 0 | **40+ 条**（`/manage/{account,data,market,merchants,order,params,product,settle,shop,sign,test}`） |
| 参数语义 | 猜 | **直接读**（如全站核心对象 `business_id` 来自 `localStorage.getItem(email+"businessId")`） |
| 渲染方式 | 无法判 | **可判 XSS**（见下） |
| 新增前缀 | 无 | `/channel003/*`、`/channel100/*`、`/jdd_api/test_tools/*`、`/pop/assist/*` |

### 15.4 ★ 用 chunk 判定存储型 XSS 的正确姿势

拿到消费代码后，**只看待渲染值是不是作为 React/Vue 的「文本 children」传递**：

```js
// ✅ 安全：第三参数是 children ⇒ React 自动 HTML 转义
p.a.createElement(Mt.a.Option, {key:e.first_category_id, value:e.first_category_id}, e.first_category_desc)

// ❌ 危险：dangerouslySetInnerHTML / v-html / innerHTML = / insertAdjacentHTML
```

**必做第一步：把 `dangerouslySetInnerHTML` 的命中位置逐个看上下文**。
乐信亲例：全量 83 chunk 里 13 处命中，**全部在 react-dom 内部实现**
（函数体里出现 `Error(a(91))` / `_wrapperState` / `memoizedProps` / `_commitHookEffectList` 等）⇒ **业务零使用**。

⇒ 结论：**库里有 `<script>alert('XSS')</script>` 只能证明「输入未过滤」，不能定 XSS**。
要定 XSS 必须同时满足：① 输入未过滤（存进去了）② **输出端未编码** ③ 有写入权限 ④ 目标页面真的会渲染该数据。
**四个条件缺一不可**，别只凭第①条写报告。

### 15.5 ★ 越权判定：先找一个「自己本来就该没权限」的基准

乐信亲例判定 `business_id` IDOR 的关键不是猜 id，而是**先证明自己没有合法访问权**：

```http
GET /route0007/s2s/account/info.json     （带自己的会话）
→ {"business_id":"", "mobile":"…", "email":"…"}     ← 自己是空号，没绑任何商户
```

有了这个基准，再传 `business_id=1/2/100`，服务端回：

```json
{"result":10981283,"res_info":"商户不允许越权访问，商户【】没有访问商户【1】数据的权限"}
```

⇒ **专门的越权拦截层**（不是"参数无效"，而是**主动比对会话商户与目标商户并回显双方**）。
这是**最强的不成立证据**：服务端确实消费了参数、也做了权限比对。

**方法论**：判越权缺的不是 payload，而是**对照系**。要么「自己的对象 A」对「别人的对象 B」，
要么「本该无权访问的自己」对「任意目标」。**能证明"我本无权"，剩下就是一次请求的事。**

> ⚠️ 判定脚本的自身缺陷也要防：**「`"result":0` 开头」不等于「有数据」**。
> 亲例把 `19261002 输入参数错误`、`52001520 系统异常` 这类**错误码响应**也判成了"未授权有数据"。
> 正确判据：**`data.result == 0` 且 `result_rows` 非空数组 / 非空对象**。

---

## 16. 网关「请求跨域了 / 暂无权限访问」类来源校验 —— 6 组对照判定法（2026-09-19 乐信鼎盛实证）

### 16.1 症状

访问一个从内部系统前端挖到的接口（`panshi.dszc-amc.com/rc_oa_gateway/firm-platform-serve/getPublicUrl.json`），
返回：

```json
{"rc_gateway_ip":"10.16.61.237","retmsg":"抱歉，您暂无权限访问，请求跨域了","retcode":"16051032","resultRows":[]}
```

**看着像"改个 Referer 就进去了"** —— 但**别直接下结论，也别硬顶**。

### 16.2 判定法（固定基线 + 6 组对照）

| # | 对照 | 目的 |
|---|---|---|
| 1 | **基线**：`Referer=<登录页>` + `Origin=<站点>` | 复现 |
| 2 | **完全不带** `Referer` / `Origin` | 判定是否"没带才拒" |
| 3 | `Referer=<站点根>` | 判定是否路径级白名单 |
| 4 | `Referer`+`Origin`=**同族子域**（如同网关下的另一个站） | 判定是否域级白名单 |
| 5 | `Origin: null` | 判定是否处理空 Origin |
| 6 | `Referer=<外域>` | 判定是否"白名单/黑名单"模式 |

**判读**：
- **6 组响应逐字节一致**（剔除负载均衡会变的字段，如 `rc_gateway_ip`）⇒ **该判定不基于 Referer/Origin**
  ⇒ 是**服务间调用来源限制**（需要内部调用标识/特定 Host/内网来源）⇒ **公网无参照物，未授权不成立，收工**。
- 出现**任何一组**响应不同 ⇒ 该头参与判定，可继续深挖（但仍只做对照，**不伪造 `X-Forwarded-For`、不改 `Host` 硬顶**）。

乐信亲例：6 组全同（仅 `rc_gateway_ip` 在 `10.16.61.237` / `10.16.62.137` 间轮换）⇒ 判"不成立"。

### 16.3 顺带拿到的（同一响应里的副产品）

- **`rc_gateway_ip` 泄漏内网 IP** ⇒ **低危信息泄漏**，且是后续 SSRF/内网探测的有用拼图，**记下来**
- **网关错误码**（`16051032`）⇒ 进入该网关的错误码字典

### 16.4 ★ 同族系统交叉对照：一次定位"路径属于哪个网关"

同一个路径打在**同族的多个站**上，响应形态能直接告出架构：

| 响应形态 | 含义 |
|---|---|
| 网关 JSON（`{"retmsg":..,"retcode":..}`） | **该路径属于这个站的网关**（有效路径，只被来源/权限挡） |
| **SPA 外壳 HTML**（长度与首页一致） | 该路径**不在此站网关**，被前端 catch-all 吞掉 |
| **Spring Boot 默认 404 JSON**（`{"timestamp":..,"status":404,"error":"Not Found"}`） | 该 host 是**独立 Java 服务**，路径确实不存在 |

乐信亲例：同一条路径 → `panshi` 返网关 JSON（有效）、`cia` 返 SPA 外壳、`ciaapi` 返 Spring 404
⇒ 一次就确定"这个接口在 panshi 的网关后面"，不用逐个猜。

### 16.5 ★★ 批量未授权测试：先认清「四种墙」，否则命中全是假阳性（2026-09-21 理想 C 类 71 站实证）

> 场景：**71 个"仅登录"系统的未授权批量测试**（700 个 `(host,接口)` 组合）。**真命中 0 条**，
> 但过程中被假阳性骗了一轮 —— 下面是可直接复用的判据。

**四种墙（未登录一律被拒的四种形态）**：

| 墙 | 响应原文 | 本次次数 | 位置 |
|---|---|---|---|
| **A 业务码墙** | `{"code":100012,"msg":"没有接口访问权限"}` | 174 | `api-boss-public` / `api-web` / `aisp-*` |
| **B 文本墙** | `{"errors":[{"message":"没有接口访问权限","error_code":"SYSTEM_NON_PERMISSION"}]}` | 83 | **`osd-api-public` 全站** |
| **C 应用白名单** | `{"message":"api app is not in whitelists","code":403}` | 29 | `api-gateway.lixiangoa.com` |
| **D 参数校验** | `{"code":100002,"message":"缺少必要的请求参数"}` | 1 | 同 lixiang.com |

★★ **两个必踩的假阳性（本次各踩一次）**：

1. **HTTP 200 + 业务码 403** —— C 形态即此：**HTTP 状态码 200**，但 JSON 里 `"code":403`。
   ⇒ **只看 HTTP 状态码会把「应用白名单拒绝」误判成「未授权可访问」**。
   **判据：命中判定必须同时看 ① HTTP 状态 ② Content-Type ③ body 里的业务码/关键词。**
2. **SPA catch-all 冒充接口** —— `asset-vehicle-web.lixiangoa.com/api/v1/*` 全部返回
   **200 + 2593B SPA 壳**（该 host 不反代 API，`/api/*` 落前端兜底）。
   ⇒ **判据：`text/html` 或 body 以 `<!DOCTYPE`/`<html` 开头 ⇒ 一律不算命中。**

**可直接复用的批量流水线**（本次落地在 `理想_dig/recon/`）：

```
crawl_c_js.py   抓 N 个站首页 → 提 <script src> → 汇总 JS 清单
c_dig_js.py     下载 JS（跳第三方统计、优先自家域）→ grep 接口/host/密钥/路由
c_unauth.py     按 (目标host, 接口) 全局去重 → 优先 API 网关+高价值路径 → 无 Cookie 逐个 GET
```

**三个关键设计**：
- **接口要打在正确的 host 上**：前端相对路径（`/api/v1/xxx`）真实落在 **JS 里 `externalServices` 配置的 API 网关上**，
  不是当前站 —— **打错 host 只会收获 SPA 壳**（本次第一轮就是这么被骗的）。
- **写类路径预过滤**：`save|update|delete|create|submit|send|sms|upload|logout|reset|pay|export|download` 一律跳过。
- **每站首页都值得抓**：71 站首页 → **379 个 JS 引用** → 下载后挖出 **818 个接口 + 161 个自有 host**
  （含 44 个内网 k8s 域名）—— **JS 是内网测绘的最佳来源，比端口扫描干净得多**。

**顺带的定级认识**：员工/合作伙伴域的系统（本次 71 个），**无账号时未授权面为零是设计使然**，
不是"防守好"也不是"没挖到" —— 报告要这么写，别自我否定。

---

## 17. ⚠️ 环境坑：`python -u xxx.py | head -N` 会 **SIGPIPE 杀掉脚本**

**症状**：脚本跑完"看起来正常退出"（`exit=0`），但**该落盘的文件一个都没生成**（或只生成前几个）。

**原因**：管道下游 `head -N` 读够 N 行就关闭管道 → 上游 Python 写入时收到 **SIGPIPE** → 进程被终止，
**中途的写文件代码从未执行**。

**正确做法**：

```bash
python -u script.py > out.log 2>&1     # ✅ 重定向到文件
tail -50 out.log                       # 之后再看
# ❌ python -u script.py | head -50    ← 会杀脚本
```

**排查信号**：脚本里明明有 `json.dump(...)`，却"落盘为空" + 输出只到某一行就断
⇒ 先怀疑被管道截断，而不是逻辑 bug。

**关联**：与本库既有的"长枚举脚本会被 SIGTERM 杀 → 分批 + 每行 flush 落盘"是同一类问题，
处置方式统一为「**输出重定向 + `flush=True`**」。

---

## 18. ★★ 批量打网关接口时，**盯住「哪一个响应跟其他不一样」**（2026-09-19 乐信实证，本方法论直接挖到一个中危）

### 18.1 场景

一个网关（`openmoa.oa.fenqile.com/oa/*`）下从**前端**里提取到 **150 个接口**。
批量未登录打一遍，**148 个**整齐返回：

```json
{"interface_info":{...},"retmsg":"您还没登录或者登录已过期","retcode":19002028}
```

**只剩下 2 个不同**：

```json
{"result_rows":[],"retmsg":"参数url缺少","retcode":"10001"}
```

### 18.2 判读：`10001` 是**参数校验**错误 ⇒ **校验顺序缺陷**

- `19002028` = **登录校验**先执行 ⇒ 挡住了
- `10001 参数url缺少` = **参数校验**先执行 ⇒ **登录校验还没跑到**

**⇒ 只要把缺的参数补上，就有可能跳过登录校验直达业务逻辑。**

补参验证（只传无害值）：

```http
GET /oa/gongyi/get_qy_weixin.json?url=https://example.com/
→ {"result_rows":{"signature":"5164914519a411e842271c7745f91b9472b313f3",
                  "appid":"ww66c2305251a9903d",
                  "noncestr":"Wm3WZYTPz0wzccnW","timestamp":1789749494}}
```

**⇒ 未登录拿到企业微信 JS-SDK 签名**（`jsapi_ticket` 衍生物，官方标注"不可泄漏"）⇒ **成立**。

### 18.3 关键加固证据：**换参数值，看输出是否跟着变**

| 传入 `url` | 返回 `signature` |
|---|---|
| `https://mleco.oa.fenqile.com/` | `ce4a7bed…` |
| `https://example.com/` | `5164914…` |
| `1` | `c1df915a…` |

**签名随 url 变** ⇒ ① 服务端**真的为调用方给定的 url 计算签名**（不是固定串）；② **没有域名白名单**
（外域、非法值都签）—— 这正是企微官方禁止的用法，是**从"参数错误"升级为"中危凭证泄漏"的决定性一步**。

### 18.4 顺带：`url` 参数**不是 SSRF**

同名参数在别的场景常是 SSRF 入口，这里**不是** —— 判据：
**换任意 url（含外域、非法值）响应形态与耗时都不变，且只在签名值上体现差异**
⇒ 它是**签名算法的输入**，不是"服务端去请求它"。
（要证 SSRF 需要看到 `url` 指向内网时行为不同 —— **但按红线不测内网地址**。）

### 18.5 可复用清单

| 观察 | 结论 |
|---|---|
| 大批接口整齐返回同一个"未登录"码 | 鉴权正常 |
| **个别接口返回"参数错误/参数缺少"** | ★ **校验顺序缺陷，优先补参** |
| 补参后返回**实体数据/凭证** | ★★ **未授权成立** |
| **换参数值，输出跟着变** | 该参数参与**计算**（签名的输入）⇒ 找它的白名单缺失 |
| 换任意值输出形态与耗时都不变 | 参数**不被消费**（或只是回显）⇒ 别当 IDOR |

### 18.6 纪律

- 补参只用**无害值**（本域公开页 / `example.com` / `1`），**绝不传内网地址、云元数据、localhost、file:// gopher:// dict://**
- 拿到的是**签名/凭证**就到此为止 —— **不要拿着它去实际调用下游平台接口**（那是另一层越界）
- 报告里要写清"**证明了什么**"与"**没证明什么**"（本次：证明未授权下发签名；**未**证明签名在企微内一定初始化成功，后者取决于企微可信域名配置，交甲方复核）

---

## 19. ★ 微信 / 企业微信 JS-SDK 签名泄漏的**危害边界**与定级口径（2026-09-19 补充）

> 场景：未授权拿到 `signature` + `appid` + `noncestr` + `timestamp`（C-3），要判它值多少级。
> **别写成"获取敏感凭证"就完事，也别吹成高危 —— 它的危害是有条件兑现的。**

### 19.1 签名在链路里的位置

```
企业微信后台 --签发--> jsapi_ticket（企业级票据，2h，官方定性不可泄漏）
                        |
           服务端：signature = sha1("jsapi_ticket=..&noncestr=..&timestamp=..&url=..")
                        |
           前端：wx.config({appId, timestamp, nonceStr, signature, jsApiList})
                        |
           客户端：用【当前页面 URL】重算比对 + 校验域名
```

`appId` / `timestamp` / `nonceStr` **都是明文**，`jsapi_ticket` 只存服务端
⇒ **`signature` 是前端唯一拿不到、也是唯一能证明"我是这个官方应用"的参数。**

### 19.2 拿到签名后能调什么（`wx.config` 层）

| 类别 | JSAPI | 效果 |
|---|---|---|
| 定位 | `getLocation` | 精确经纬度 |
| 扫码 | `scanQRCode` | 调起扫一扫读任意码 |
| 相册/拍摄 | `chooseImage` `uploadImage` `getLocalImgData` | 读取并回传用户图片 |
| 录音 | `startRecord` `uploadVoice` | 录音上传 |
| 会话 | `openEnterpriseChat` | 打开指定成员/群 |
| ★ 界面伪装 | `hideMenuItems` `hideAllNonBaseMenuItem` | **隐藏右上角菜单 ⇒ 页面无法被举报/返回上级**，钓鱼可信度大增 |
| 分享伪造 | `updateAppMessageShareData` | 自定义分享卡片标题/图标/链接 |

**定性关键词**：签名是**能力凭证（capability）不是数据凭证（data）** —— 它不吐出任何用户数据，
但它让攻击者的页面在客户端内**具备官方应用的外观与能力**。写报告时这么表述最准确。

### 19.3 ★★ 兑现门槛：**可信域名**（决定中危 vs 高危）

| 路径 | 结果 |
|---|---|
| **A** 攻击者自建域名页面 + 拿到的签名 | ❌ **必失败**。客户端校验「当前页面 URL 的域名 ∈ 应用配置的可信域名」，不在则 `invalid signature`。 |
| **B** **可信域名下拿到内容注入点**（XSS / 可控 HTML / 富文本 / 上传的 HTML 文件）+ 签名 | ✅ `wx.config` 成功 ⇒ **调用任意 JSAPI** |

★ 注意：**`wx.config` 的 `url` 由客户端自动取 `location.href.split('#')[0]`，不是前端传参**
⇒ **攻击者无法"指定" url**，只能在自己能控制的页面 URL 上 config
⇒ **"对任意 url 都签名"这个缺陷本身不等于任意页面可用**，它只证明：① 服务端真为调用方给定值算签名
② **没有域名白名单**（企微官方明令禁止的用法）。

### 19.4 三条加重情节（有则写进报告，无则别硬凑）

1. **实时性**：接口对任意 `url` **现算现给**（不是一次性泄漏一个签名）。`jsapi_ticket` 2h 一换，
   但接口能跟着换 ⇒ **等于持续持有签名能力，直到修复**。比"泄漏一个静态 signature"严重得多。
2. **白名单缺失**：换 `url` 值签名跟着变 ⇒ 服务端确实在**为调用方给定的任意 url** 计算 ⇒ 是本缺陷的核心。
3. **门槛已有拼图**：同目标下若已存在可信域名内的内容可控面（富文本、可上传 HTML、自定义 H5、
   渲染型接口），**任一注入点成立即可把中危升为高危**。

### 19.5 定级口径（建议）

- **单独看 = 中危**：未授权凭证下发 + 校验缺失（域名白名单 / 登录校验顺序），
  但**兑现还需额外一个注入点** ⇒ 不满足"可直接利用"。
- **升为高危的唯一条件**：同域内找到内容注入点（能证明路径 B 的第二步）。
- **报告必须写清"证明了什么 / 没证明什么"**：
  证明"未授权下发签名"；**未**证明签名在企微内一定 `config` 成功（取决于甲方企微后台的可信域名配置）
  ⇒ **交甲方复核**。这句话能让报告不被撤。

### 19.6 红线

- 拿到签名**不要拿去实际调用下游平台接口**（那是另一层越界，且需要真实企微环境）
- 验证 `url` 只用**无害值**：本域公开页 / `example.com` / `1`。
  **绝不传内网地址、云元数据（`169.254.169.254`）、`localhost`、`file://` `gopher://` `dict://`**
- 顺手判一下「`url` 参数是不是 SSRF」：**换任意值响应形态与耗时都不变、只在签名值上体现差异**
  ⇒ 它是**签名算法的输入**，不是"服务端去请求它" ⇒ 不是 SSRF。

### 19.7 修复建议（按根因→加固排序）

1. **登录校验前置**（根因：参数校验跑在登录校验之前，见 §18）
2. **`url` 做可信域名白名单** —— 只对自家可信域名签名
3. **`noncestr` 改真随机**（亲例：硬编码 `Wm3WZYTPz0wzccnW`）
4. 补 `Referer` / `Origin` 校验 + 加频控

### 19.8 ★ 往上找一层才是真高危

同一网关里如果哪个接口泄漏的是 **`access_token`**（换 `jsapi_ticket` 的**上游**，能直接读写通讯录、发消息、
改应用配置），那就是**无条件的直接高危**。见到 JS-SDK 签名类缺陷，**顺着同一个网关往上游找 access_token / corpsecret**。

### 19.8.1 ★ 复核实测（2026-09-19，乐信）

**① 签名口仍存活且仍无白名单**（复核 2 次）：

| 传入 `url` | 返回 `signature` |
|---|---|
| `https://mleco.oa.fenqile.com/` | `30da00516814d6aff83af192c0a2f39d7a99c1da` |
| `https://oa.fenqile.com/` | `241c688d4d757c0859438256d955211ed1c3d39d` |

⇒ 同一 `noncestr`（硬编码 `Wm3WZYTPz0wzccnW`）、同一 `appid`，**换 url 签名必变** ⇒ 缺陷稳定存在、非偶发。

**② 同族 `get_lexingongyi_access.json`（名字带 `access`，§19.8 指的最危险方向）—— 已排除**：

| 请求 | 响应 |
|---|---|
| `?url=<本域>` | `62001001 token获取错误，请检查` |
| `?url=<本域>&code=test123` | 同上 |
| `?url=<本域>&appid=ww66c2305251a9903d` | 同上 |

⇒ 服务端**取 token 失败，未返回任何凭证** ⇒ **不存在 access_token 泄漏**。
**⇒ 本类缺陷（JS-SDK 签名）的上限就是中危，不会因为同族接口升成高危。**
（这是一个重要的**负向结论**：排查同类目标时，"名字里带 access/token 的兄弟接口"必须先补参打一遍再定级。）

**③ 附带：网关回显行为** —— `interface_info.interface_request` 会把**请求参数原样回显**
（`url` / `code` / `appid` 都出现在响应里）。这是**请求回显**，只回显调用方自己发的内容，
**不是他人数据泄漏** ⇒ 记录，不单独成报告。但注意：若哪天有参数携带**会话票据**，
回显就会进日志/前端 ⇒ 提一句"敏感参数勿走 query"。

---

## 20. ★ 未授权可达的反序列化面：fastjson 指纹识别、WAF 拦截页判读、以及武器化前的用户同意纪律（2026-09-19 乐信 datashare 实证）

### 20.1 fastjson 指纹：一句异常原文就够

把 JSON 字段喂成**类型不符**的值，读回显的异常原文：

| 回显 | 框架 |
|---|---|
| **`can not cast to JSONObject.`** | **Alibaba fastjson**（本次亲例） |
| `Syntax error, expect {, actual ...` / `autoType is not support` | Alibaba fastjson（另一种分支） |
| `Unrecognized field ... not marked as ignorable` | Jackson |
| `Expected BEGIN_OBJECT but was ...` | Gson |

乐信亲例（`POST /apps/gateway/internet/login`，`param` 字段）：

```
param={}   → 200 {"code":1,...,"data":"行为验证码二次验证不通过"}
param=[]   → 200 {"code":1,...,"data":"can not cast to JSONObject."}   ← ★ fastjson 指纹
param=null → 200 {"code":1,...,"data":""}                              ← 不解析
```

★ **关键价值不只是指纹，而是「解析发生在鉴权/风控之前」** —— 不带有效验证码（`param=[]`）也能触达反序列化，
说明该字段是**未授权可达的反序列化点**。**判定顺序**：先看「解析错误 vs 业务错误」哪一类先出现。

### 20.2 ★ 怎么分清「WAF 拦截页」与「业务响应」

同一次测试里，同一个 URL 会出现两种完全不同的响应形态：

| | 业务响应 | WAF 拦截页（本次亲例） |
|---|---|---|
| 状态码 | 200 | **501**（也可能是 403/412） |
| Content-Type | `application/octet-stream` | `text/html` |
| 体积 | 43~79 B | **693 B（固定）** |
| 特征 | 业务 JSON | `<!-- event_id: 6cb8f777... -->` + `Server: qcloud-txcloud2026-nginx-proxy-10-72` |

**判据（三条里中两条即可定性）**：① 出现 `event_id` / `EVENT ID` / 固定模板；② 体积固定且远大于业务响应；
③ 与业务响应**形态完全不同**（HTML vs JSON）。

★ **对照法**：同一次会话里先取一条**正常业务响应**做基线（本亲例 `param={}` → 200/79B），
再发测试载荷；**形态突变 = 被拦，不是应用拒绝**。

### 20.3 ★★ 遇到 WAF 拦了 RCE 类向量：记录、停手，武器化前须用户同意（2026-09-19 修订）

本次：`param={"@type":"zzz.nonexistent.Cls9F3A"}`（**只用不存在的类名，不带任何 gadget**）→ 501 拦截页。

**处置纪律（2026-09-19 三次修订 —— 原文「一律不绕」过严；武器化改为须用户同意；但打崩服务属 DoS 绝对红线，仍不做）**：

> **可以绕 WAF，但只能在「探针不执行」的前提下绕。** 分界线画在 payload 上，不画在手法上。

1. **✅ 允许**：用**非执行探针**试各种 WAF 绕过手法，目的是**测出 WAF 规则的真实覆盖度**（= 这个控制到底管不管用）。
   非执行 = 类名不存在（`Class.forName` 失败即抛异常）/ 白名单类 / 无害值 —— **任何情况下都不会执行代码**。
   手法随便试：大小写、`\u` 转义、无引号、单引号、注释、multipart、query 承载、编码叠加……
2. **⚠️ 武器化前须用户同意**：一旦某个手法**穿过了 WAF**，把探针换成 ② 类载荷之前，
   **必须先按 §25.1 向用户说明后果（投什么载荷 / 目标上会发生什么 / 副作用与影响面 / 怎么中止），取得明确同意** ——
   **让目标加载远程类**的 JNDI/LDAP/RMI（下发 reference / class）、`TemplatesImpl`、远程类加载、文件写入、第二段载荷。
   那已经不是"测覆盖度"，而是**对生产系统实际发一次 RCE**；**未获同意即不做**。
   ★ **且若该载荷可能打崩服务 / 资源耗尽 ⇒ 属 DoS 绝对红线，仍不做（用户同意也不做）。**
   ★ **例外（① 类，可做，无需询问）**：**仅解析 / 无载荷回连** —— DNS 型 OOB（`Inet4Address`、`dnslog` 域名一类）
   或**空响应 Listener**（只记录连接，不下发任何 class / 不返回可反序列化对象），纪律见 §25.1。
3. **⚠️ 也不做**：纯粹为绕过 WAF 检测阈值而做的手法（大体积填充等）—— 到那一步手法本身已无诊断价值，
   唯一目的只剩投递 payload。**收益/风险不划算，不做。**
4. **报告写法**（三段缺一不可）：① 列出**尝试过的手法矩阵 + 每一条的 WAF/应用结果**；
   ② 说明**哪些手法穿过了 WAF**（这就是给甲方的价值 —— WAF 配置缺陷）；
   ③ 明确写「**未触达目标行为 / 当前不可利用**」+「**不可依赖 WAF 作为该风险的主要控制**」。
5. **报告中必须写清两句话**：
   - 「`@type` 在公网路径被 WAF 挡死 ⇒ **该向量当前不可利用**」；
   - 「**不能据此断定服务端安全** —— 要下结论必须服务端侧确认版本与 `safeMode`/autotype 白名单」。
   **这两句缺一，报告就是过度断言。**
6. **不要写「存在 fastjson 反序列化 RCE」**。可写的是：「未授权可达的反序列化点 + 框架指纹 + 外围有 WAF 特征拦截，
   建议服务端自查」。这是**加固建议**，不是漏洞结论。
7. 顺带产出：拦截页泄漏的**代理主机名**（`qcloud-txcloud2026-nginx-proxy`）、**event_id**（甲方可用它查日志溯源）——
   写进报告对甲方有价值。
8. ★ **与 §25 的分档对齐（2026-09-19）**：本节管的是 **② 类（武器化 / 需先绕安全机制）** ⇒ **须先取得用户同意**（§25.1）；
   ① 类**只读最小命令证明**（`id` / `whoami`，单发只读非破坏）不在本节限制内，见 §25.1。

---

## 21. ★★ 用「通过/拦截」矩阵反推 WAF 规则的真实形态（2026-09-19 datashare 实证，12 组对照）

> 目的不是"绕过"，而是**知道这条规则到底长什么样** —— 从而告诉甲方它哪里漏。
> 这套方法本身零风险：每一发都用**不存在的类名**，WAF 拦不拦都不执行代码。

### 21.1 设计思路：**把「位置」当自变量**

关键在于**沿位置维度做正交对照**，而不是盲试编码变形。看「同一个字符串出现在不同位置会怎样」：

| 自变量 | 对照载荷 | 若通过说明 |
|---|---|---|
| **值位置** | `{"x":"@type"}` | 规则只认键位置（不是子串匹配）——**通过 = WAF 是结构感知的** |
| **键位置（基线）** | `{"@type":"…"}` | 基准拦截 |
| **单引号键** | `{'@type':'…'}` | 规则是否覆盖单引号 |
| **注释包裹** | `{/*x*/"@type":"…"}` | 规则是否会被注释打乱 |
| **无引号键** | `{@type:"…"}` | 规则是否要求引号 |
| **大小写** | `{"@TYPE":"…"}` | ★ **规则是否大小写敏感** |
| **`\u` 转义** | `{"\u0040type":"…"}` | WAF 是否解码 unicode 转义 |
| **全转义** | `{"\u0040t\u0079pe":"…"}` | 同上（确认非单点规则） |
| **multipart 承载** | 同键位置，改 `Content-Type: multipart/form-data` | WAF 是否解析 multipart 分段 |
| **query 承载** | `?param={"@type":"…"}`，body 只留其它字段 | WAF 是否只查 body |
| **对照复核** | 结尾再发一次基线 | **确认 WAF 测试全程有效**（防"WAF 刚好关了"误判） |

### 21.2 反推结论（datashare 亲例）

把结果按位置排列，规则形态就浮出来了 —— 近似 **`["']@type["']\s*:`**（引号 + 键位置 + **大小写敏感**）：

- 值位置不匹配 → 通过 ✔；键位置 3 种写法（双引号/单引号/注释后）全匹配 → 拦 ✔
- **无引号 → 通过**、**大小写 → 通过** ⇒ 两者都是**规则的真实缺口**

### 21.3 ★ 最有价值的一句话：分清「防护有效」与「巧合互补」

datashare 这次有两个手法**确实穿过了 WAF**：
- `{"@TYPE":…}` → 穿过 WAF，但 **fastjson 的 autotype 键也要求精确小写 `@type`** ⇒ 目标行为未触发
- `{@type:…}` → 穿过 WAF，但**应用解析器更严格**，报 `illegal identifier` ⇒ 未触达

⇒ **这不是"防护有效"，是"两个独立的宽松点恰好互补"。**
**报告里必须写成**：`@TYPE` 与无引号形式**100% 穿过 WAF**，规则**依赖"应用比 WAF 更严格"这一脆弱前提**；
若服务端换用大小写不敏感解析器、或规则被复用到别的组件，立刻失效。
**⇒ 修复优先级：服务端 > WAF。**（WAF 只加 `(?i)` 并覆盖无引号/转义/空白，不能当作该风险的主要控制。）

### 21.4 副产品：一次顺带挖到的接口行为

对照里带上 `?param=[]` 得到 `can not cast to JSONObject.` ⇒ **证明应用从 query string 也读该参数**
（Spring `@RequestParam` 同时取 query 与 form）。这类"位置诊断"经常顺手挖出**参数来源扩大**的信息，
值得固定成套路：**同一参数分别从 body / query / header 各送一次，看应用收不收。**

---

## 22. ★★ fastjson 的 WAF 绕过手法清单 —— 与「腾讯云 WAF 实测」的差异（2026-09-19 datashare 实证）

### 22.1 公开流传的 fastjson 绕过手法（网上能查到的全集）

**前提知识**：fastjson 会自动对**键与值**做 **unicode(`\uXXXX`) 与 hex(`\xXX`) 解码**；
`skipWhitespace` 会跳过 `\b \n \r \f \t` 与 `/` 开头的注释。所以下列写法在 fastjson 侧**都等价于 `@type`**：

| # | 手法 | 写法 |
|---|---|---|
| 1 | unicode 转义 | `{"\u0040\u0074\u0079\u0070\u0065":…}` |
| 2 | **hex 转义** | `{"\x40\x74\x79\x70\x65":…}` |
| 3 | 控制字符填充（键后） | `{"@type"\b:…}` |
| 4 | 换行填充 | `{\n"@type":…}` / `{"@type"\n:…}` |
| 5 | 注释填充 | `{/s6/"@type":…}` / `{/**/…/**/,"@type":…}` |
| 6 | 大量 `/**/` 脏数据 | `{/**//**//**/…/**/,"@type":…}` |
| 7 | **multipart + `Content-Transfer-Encoding: base64 / quoted-printable`** | 分段体用 QP/Base64 编码，WAF 不解码 |

来源：绿盟技术博客《fastjson 浅谈》·腾讯云社区《Fastjson:我一路向北(下)》·whoopsunix.com。

### 22.2 ★★ 腾讯云 WAF（`qcloud-txcloud*-nginx-proxy` + `event_id` 拦截页）实测

| 手法 | 结果 |
|---|---|
| 明文 `{"@type":…}` | 拦 501 |
| `\u0040…` / 全 `\u` | **拦** ⇒ WAF **会解码 unicode** |
| **`\x40\x74\x79\x70\x65`（hex）** | **拦** ⇒ ★ **WAF 也会解码 hex**（公开资料说"可绕"的这条**对腾讯云无效**） |
| **`{"@type"\b:…}`（0x08 填充）** | **拦** ⇒ WAF 会规范化控制字符，规则**不是**简单 `\s*` |
| 单引号 `{'@type':…}` | 拦 |
| 注释 `{/*x*/"@type":…}` | 拦 |
| multipart（明文 / `\u0040`） | 拦 ⇒ WAF **解析 multipart 分段** |
| **multipart + `CTE:base64`** | 拦 |
| **multipart + `CTE:quoted-printable` + `{"=40type":…}`** | **✅ 穿过 WAF** |
| HPP `param=safe&param={"@type":…}` | 拦 ⇒ WAF **检查全部同名参数** |
| query 承载 `?param={"@type":…}` | 拦 ⇒ WAF **也查 query string** |
| **`{"@TYPE":…}`（大小写）** | **✅ 穿过 WAF** |
| **`{@type:…}`（无引号）** | **✅ 穿过 WAF** |

### 22.3 ★★★ 三条最值钱的教训

**① 公开资料里的「可绕 WAF」手法，必须对本厂商实测。**
本次最反常识的一条：**`\x` hex 转义**在绿盟与腾讯云社区的文章里都写着"可应对关键字封禁"，
但**腾讯云 WAF 自己会解码 hex** —— 拿公开 payload 直接打就是白费一轮。
**⇒ 见到"某手法可绕 WAF"的说法，先当成待验证假设，用**大小写/转义/位置**的正交矩阵打一遍再下结论（见 §21）。**

**② 绕过了 WAF ≠ 打通了。要同时确认「应用侧认不认这个写法」。**
本次有**三个手法确实穿过 WAF**，全部被应用侧堵死：
- `@TYPE` → 穿过 WAF，但 **fastjson 的 autotype 键要求精确小写** ⇒ 目标行为未触发
- `{@type:` → 穿过 WAF，但**应用解析器报 `illegal identifier`**（无引号键被禁用）
- `multipart + CTE:QP` → 穿过 WAF，但**应用整体丢弃带 `Content-Transfer-Encoding` 的分段**（用"CTE + `param={}`"诊断出来：响应等同 param 不存在）

**⇒ 判定绕过的完整判据是「WAF 放行 + 应用按预期解释」两条同时成立**，
只满足第一条时，报告里只能写「WAF 规则存在缺口」，**不能写「已绕过」**。

**③ 用「无损诊断载荷」把交叉点查清楚。**
本次关键一步是把载荷换成 `{}`（无 `@type`）重发一次：
- 若返回「验证码错误」⇒ 该分段被应用解析 ⇒ 编码方式有效，去调编码细节
- 若返回「等同不带该参数」⇒ 该分段被丢弃 ⇒ **整条路作废，别再花时间**
**⇒ 每次绕过尝试都要配一发"同载体 + 无害载荷"的诊断，否则会把"应用没解析"误判成"绕过失败"。**

### 22.4 通用 WAF 绕过清单（云 WAF 场景，按性价比排）

| 优先级 | 手法 | 说明 |
|---|---|---|
| ★★★ | **找源站真实 IP 直连** | 云 WAF 最经典绕过：历史 DNS、未接入 WAF 的子域、MX 记录同网段、SecurityTrails 历史解析 |
| ★★★ | **正交位置矩阵**（值/键、body/query/multipart、大小写、转义） | 见 §21，成本极低、信息量最大 |
| ★★ | **分块传输 `Transfer-Encoding: chunked`**（含延时分块） | WAF 需重组才能检测；延时分块还耗其重组线程 |
| ★★ | **charset 混淆**（`ibm037`/`ibm500`/`cp875`/`ibm1026`） | WAF 用错编码解码、后端用对 |
| ★★ | 请求走私 CL-TE / TE-CL、HTTP/2 降级 | 技术含量最高 |
| ★ | HPP（同名参数多值） | 仅在 WAF 与后端取值位置不同时有效 —— 本次腾讯云**无效** |
| ★ | 脏数据溢出（>1~4M 直接放行） | 部分云 WAF 的已知弱点；**属资源消耗型，慎用** |
| ★ | multipart / CTE 编码 | 需同时确认应用会解析 |

---

## 23. ★★★ fastjson 绕 WAF 的决定性手法：**利用「宽容解码」与「厂商 WAF 严格解码」的不对称**
> 2026-09-19 乐信 datashare 实证。**本文是 §21/§22 的结论修正，务必先读本节。**

### 23.1 §22 的结论错在哪

§22 曾写「公开流传的 fastjson 绕过手法（hex/unicode）在腾讯云 WAF 上**全部失效**，因为 WAF 也解码 hex」。
**这个结论只对「标准写法」成立**，我漏掉了**一整个类别**：fastjson 的解码器**比 WAF 更宽容**。
WAF 解得了标准 `\x40` / `\u0040`，但**解不了 fastjson 的宽容变体** —— 差异在**解码器的严格程度**，不在「解不解码」。

### 23.2 fastjson 的两处「宽容解码」（源码级依据）

**① `\x` 走 `digits[]` 查表，未占位下标默认为 0**

```java
case 'x':
    char x1 = this.ch = this.next();
    x2 = this.ch = this.next();
    int x_val = digits[x1] * 16 + digits[x2];   // digits 只在 0-9A-Fa-f 位置有值
    char x_char = (char) x_val;
```

⇒ `digits` 表**只在 0-9 A-F a-f 的位置填了真实值，其余下标默认 0**。
⇒ **`\x40` 的第二个字符可以换成任意「码点 ≤102 的非 hex 字符」**：`\x4J`(74)、`\x4Z`(90)、`\x4_`(95)、
  `\x4[`(91)、`\x4!`(33)…… 都解出 `@`。**可用字符集 40+ 个**，WAF 封一个换一个。
⇒ ★★ **但有上界：`digits` 表长只有 103（索引 0..102）**，码点 ≥103 的字符**不是"取 0"而是直接抛异常**（2026-09-24 实测）：
  `\x4g`(103) → `ArrayIndexOutOfBoundsException: Index 103 out of bounds for length 103`；
  `\x4j`(106) → `Index 106 out of bounds for length 103`。
  ⇒ **不是"任意非 hex"** —— `g`~`z`、`{|}~` 这些会**报错而非解出 `@`**，挑字符时避开。
⇒ 但 WAF 的正则/解码器看到 `\x4J` **不是合法转义**，原样保留 ⇒ 字面量里没有 `\x40`，也没有 `@type`。

**② `\u` 用 `Character.digit(c, 16)`，它认非 ASCII 数字**

```java
case 'u':
    char c1 = this.next(); char c2 = this.next();
    char c3 = this.next(); char c4 = this.next();
    int val = Integer.parseInt(new String(new char[]{c1,c2,c3,c4}), 16);  // 早期版本用 Character.digit
```

`Character.digit(c, 16)` 不只看 ASCII `0-9a-f` —— **全角数字（`０` U+FF10）、泰文数字（`๐` U+0E50）等大量
Unicode 数字都能冒充 hex**。⇒ `\u００４０`、`\u๐๐๔๐` 都解出 `@`（**2026-09-24 本地实测确认**），字节特征与 `\u0040` 完全不同。

★ **边界（实测，别用错）**：实现是 `Integer.parseInt(s, 16)` —— **第一遍用 `Character.digit`（认 Unicode 数字）、
第二遍溢出检查用严格数字比较**，所以：

| 写法 | 结果 |
|---|---|
| `\u0040`（ASCII） | ✔ = `@` |
| `\u00４0`（全角４） | ✔ = `@` |
| `\u00๔0`（泰文๔） | ✔ = `@` |
| `\uZZ40`（字母 Z） | ✘ `NumberFormatException: For input string: "ZZ40"` |
| `\u4J00`（字母 J） | ✘ `NumberFormatException: For input string: "4J00"` |

⇒ **只有「Unicode 数字」能冒充，字母不行** —— 与 `\x` 的机制（查表）完全不同，字符集也不同，
**WAF 必须分别处理这两条**。

**③ 版本无关性（2026-09-24 本地跨版本实测，回答"是不是只有低版本才这样"）**

| 版本 | `\x4J` → `@` | `digits` 表长 |
|---|---|---|
| 1.2.24 | —（该版本在 `JSON.parse` 路径下**连字面 `@type` 都不处理**，当普通字段 ⇒ 转义无从体现） | 103 |
| 1.2.47 / 1.2.48 / **1.2.48.sec10** / 1.2.55 / 1.2.58 / **1.2.60** / **1.2.60.sec10** / 1.2.62 / 1.2.66 / 1.2.68 / 1.2.75 / 1.2.80 / 1.2.83 / **1.1.46.sec06** | ✔ **全部成立** | 103（越界文案逐字相同） |
| **fastjson2 2.0.65**（核心，`com.alibaba.fastjson2`） | ✔ **成立** | **103（同）** |

⇒ ★★ **跨 `1.2.60` 无任何行为变化；连 `.sec` 安全修复版也照样成立。**

★★★ **辟谣：网上/AI 常说的「< 1.2.60 才受影响、1.2.60 已修复、`.sec` 版安全」——核心论断全错。**

| 说法 | 判定 |
|---|---|
| `1.2.60`（2019-09-04 发布）修复了此问题 | ✘ **错**：1.2.60 实测未修（发布日期属实，我从 Maven Central 核到 `Last-Modified: Wed, 04 Sep 2019 08:54:32 GMT`） |
| `< 1.2.60` 受影响、`>= 1.2.60` 安全 | ✘ **错**：1.2.60/62/66/68/75/80/83 **全部照样成立**，fastjson2 2.0.65 也成立 |
| `.sec` 版可免（`1.1.46.sec06` 等） | ✘ **错**：实测 `1.1.46.sec06`、`1.2.60.sec10` **都照样吃 `\x4J`** |
| `.sec` 版真实存在 | ✔ **真**：Maven Central 实有 **79 个** `.sec` 构建（`1.1.31.sec01` → `1.2.69_sec12`） |
| `.sec` 修什么 | ★ **修 autotype 黑名单**：`1.2.48` deny **43 →** `1.2.48.sec10` **110**；`1.2.60` deny **48 →** `1.2.60.sec10` **110** |
| 根因是"未校验后续字符" | ⚠ **方向反了**：后续 2 字符**被读进来当查询索引**（`next()`×2 → `istore`），真正的问题是**稀疏表 + 无上界检查**（见 ① 的字节码） |

**★ 为什么这说法错得这么像真的**：它把**真实存在的 autotype 安全修复史**（1.2.60 是真实安全版本、`.sec` 是真实补丁线）
**嫁接到一个从未被当作漏洞修过的行为上**。

**★ 最根本一条**：**`\x` 宽容解析不是"未修的 bug"，官方视为预期行为** ——
fastjson2 是**全新重写**的实现，**仍完整保留**（连 `digits` 表长 103 都没变）。
它**只在前面有 WAF 时才成为问题** ⇒ **修复责任在 WAF/网关侧**（归一化或直接拒绝非法 JSON 转义），
**升级 fastjson 到任何版本都不解决**。

★ 副产物（报告可用的历史脉络）：**fastjson deny 名单增长史**
`41(1.2.47) → 43(1.2.48) → 44(1.2.55/58) → 48(1.2.60) → 80(1.2.62) → 88(1.2.66) → 109(1.2.68) → 169(1.2.83)`，
`.sec` 线一律跳到 **110**。

★ **方法坑（别再犯）**：用「`javap` 整体输出 md5」判"某版本是否改了某段逻辑"**不可靠** ——
javap 输出含**常量池序号**，任何无关源码改动都让 md5 变。本轮 1.2.58/1.2.60/1.2.62 的 md5 确实各不相同，
但**行为逐字相同**。**判"改没改"要看行为或精确到方法的操作码序列。**
（另一个低级错误：`d41d8cd98f00b204` 是**空输入的 MD5**，出现它说明文件根本没取到，应立刻警觉。）

### 23.4 ★★ 版本指纹法（通用方法，2026-09-24 datashare 实测把 fastjson 定到 **1.2.83**）

**适用场景**：组件版本未知，但有一个「能对类名/特征值给出不同响应的 oracle」。
**核心思路**：把版本号问题转成**判别位**问题——找一个**在某版本两侧状态会翻转**的特征，一发定档。

**四步法**：

```
① 本地逐版本穷举「PASS 集」   ← 把候选特征空间整个过一遍（本目标 = 30,313 个类名 / 版本，2 秒）
② 相邻版本做差集 ⇒ 判别位     ← 状态翻转的那些特征，就是刀
③ ★ 判别位必须在【端到端】层标定，不能用内部函数返回值
④ 目标上逐发打判别位 ⇒ 收缩区间
```

**★ 第③步是这一步最容易被跳过、也最容易翻车的地方（本轮真实踩到）**：

| 入口 | `{"@type":"java.lang.Exception"}` @ 1.2.83 |
|---|---|
| 直接调 `checkAutoType("java.lang.Exception", null)` | **抛** |
| `JSON.parse("{\"@type\":\"java.lang.Exception\"}")` | ★ **不抛**，得到 `JSONObject` |

**目标侧只能观测端到端行为** ⇒ 用内部函数标定的判别表去套目标，会前后矛盾。
**规则：判别位一定要在与目标同构的入口上标定。**

**本目标的判别位（端到端，已标定，★ 2026-09-24 修正）**：

| 载荷 | ≤1.2.80 | 1.2.83 | 1.2.84 | 判别力 |
|---|---|---|---|---|
| `{"@type":"java.awt.Point"}` | 实例化成功 | ★ **`autoType is not support.`** | 抛 | ★★ **有效**（两档性质完全不同） |
| ★ `{"@type":"jar:http:…!.x.Exception"}` | 抛 | ★ **不抛（返回 null）** | ★★ **抛** | ★★ **有效，且能分 1.2.83/1.2.84** |
| ~~`java.lang.Exception`~~ / `RuntimeException` / `IllegalStateException` | 实例化 | 变 `JSONObject` | 变 `JSONObject` | ⛔ **本轮判定为零判别力**（见下） |

★★ **上表最后一行是本轮纠正的一个真实错误**：这几个名字**自带 `Exception` 后缀**，会命中 1.2.83 的
**failure-soft 分支**（`typeName.endsWith("Exception")` → `return null`）⇒ **1.2.83 起无论类在不在白名单都不抛**。
在目标上只能观测 HTTP 响应，而"实例化出 Exception 对象"与"返回 JSONObject"**在应用侧常常同形**（都是业务文案）
⇒ **用 `java.lang.XxxException` 做版本判别是无效的**。本目标此前"三发同档"的结论**只有第一发（`Point`）承重**。

**★ 有效判别位 `jar:http:…!.x.Exception` 的原理**：
1.2.84 在更早处加了「拒含 `:` `/` `!` 的类型名」（CVE-2026-16723 的修复）⇒ URL 形态**在到达 failure-soft 分支前就抛**；
而 **1.2.83 会走到末尾、被后缀放行 ⇒ 不抛**。⇒ 这一维**可以把 1.2.83 与 1.2.84 分开**。

**★ 无效判别位（各版本一致，别浪费弹药）**：`java.lang.Throwable`（一直 DENY）、
`java.util.regex.Pattern`（一直 `create instance error`）、`java.lang.AutoCloseable`（一直 `$Proxy`）、
★ **任何以 `Exception`/`Error` 结尾的类名（1.2.83 起一律不抛）**。

**★ 1.2.83 的「一刀切」特征**：PASS 集从 **118 → 86**，砍掉的 32 个 =
`java.awt.{Point,Font,Color,Rectangle}` ＋ `java.lang.*` 异常类 28 个（`Throwable` 家族）
⇒ **1.2.83 专门移除了「`Throwable` 子类 + AWT」**（配合封堵 `ThrowableDeserializer` 双层 `@type`）。
**1.2.83 与 1.2.84 的内建白名单完全相同（差集丢 0 增 0）⇒ 该维不可分；但 failure-soft 维可分（见上）。**

### 23.4.1 ★★★ fastjson **1.2.83 的 failure-soft 分支**（2026-09-24，GitHub 资料 + 本地跨版本实证）

```java
// checkAutoType 结尾（1.2.83）
if (typeName.endsWith("Exception") || typeName.endsWith("Error")) {
    return null;                       // ★ 不抛异常，解析继续
}
throw new JSONException("autoType is not support. " + typeName);
```

**三条直接影响（都是判读纪律级别的）**：

1. **纯字符串后缀检查，与是否真继承 `Exception` 无关** —— 任何名字以 `Exception`/`Error` 结尾的 `@type`
   都会走到 `return null`（实测 `java.awt.Point.Exception`、`zzz.Probe.Error` 同样不抛）。
2. ★ **`return null` ⇒ 解析不中止 ⇒ 单请求可串联多探针**（1.2.83 才成立；1.2.80 第一个就中止）：
   ```
   1.2.80  {"a":{"@type":"WireFeed.Exception"},"b":{"@type":"Thread"}}  → 报 WireFeed（首个即中止）
   1.2.83  同一载荷                                                     → 报 Thread（★ 首个被跳过、继续）
   ```
   ⇒ 在 1.2.83 目标上可用**多键对象**把多组探针塞进一次请求（注意：目标端点若做 `parseObject` 则**不能用 JSON 数组**，
   实测 `param=[]` 回 `can not cast to JSONObject.`）。
3. ★★ **公开 PoC 的 `.Exception` 后缀是承重的，不是装饰** —— `dinosn` 实验室的 MECHANISM.md 明确写：
   单请求两步链（先 `jar:http:` 把远端 JAR 缓存到 fd，再 `jar:file:/proc/self/fd/N` 加载）
   **依赖这个后缀让第一步不中止**。⇒ 复现公开 PoC 时**漏掉后缀 = 链条根本走不到第二步**。

★ **副作用（也是判据）**：该分支使「**以 `Exception`/`Error` 结尾的探针**」在 1.2.83 上**永久失去判别力**，
做版本指纹时必须先剔除这一类名字。

**★ 分辨极限的判定方法**：先找"这两版真正改过什么"，再验证那个差异**在黑盒上是否可观测**。
⚠️ **2026-09-24 修正**：本轮曾判「1.2.83/1.2.84 在黑盒上不可分」——**这个结论错了，是"选错了载荷形态"导致的**。
当时用的对照是 `jar:http:..…!.P`（**无后缀**），而 1.2.84 的新检查与 1.2.83 的 failure-soft 分支**在无后缀时恰好同形**（都抛）；
**加上 `.Exception` 后缀后立刻可分**（1.2.83 不抛 / 1.2.84 抛）。
⇒ **教训：判"两版不可分"之前，必须在同一"形态族"里穷举变体（有无后缀、点/斜杠、类名长度…），
     单点相同的结论不足以宣布"不可分"。**

**★ 判别位可信的前提**：已知目标存在"额外 deny"时（本目标 `Pattern` 被拒），**用多发放成组判读**——
**全部落在同一档 ⇒ 归因于版本；出现分裂 ⇒ 归因于配置**。
⚠️ 但成组前提是**每发都真有判别力**（剔除 `Exception`/`Error` 后缀类）。

**★ 指纹结论对报告的价值**：① 让本地复核结论**可直接映射到目标**（不用挂"版本未知"）；
② 给 CVE 排除论证**加第二重依据**（版本层）；③ 让加固建议变准 ——
★ **亲例（2026-09-24 定档 1.2.83 后）**：目标**正在 CVE-2026-16723 的影响区间内且未修复**，
唯一挡路的是**部署形态**（非 fat-jar）⇒ 此时 **"升级到 ≥1.2.84" 是有实际意义的建议**；
反过来，若原先误判成 1.2.84，就会写成"该 CVE 已修复"而**给出错误结论**。
⇒ **版本定档的精度直接决定加固建议的对错。**

### 23.5 ★★ 用【响应时间】判定「目标有没有发起外连」—— 必须用量级差分（2026-09-24 datashare 实证）

**适用**：想判"某个解析路径会不会真的去拉一个 URL / 连一个地址"，但**手上没有任何回调基础设施**。
做法：让目标去连一个**必然卡住**的地址，看响应时间是否进入"几十秒"量级。

**★ 关键设计：把预期差异放到「数十秒 vs 数百毫秒」这个量级上，不要指望数百毫秒级的差异。**

- 卡住地址选 **`192.0.2.0/24`（TEST-NET-1，RFC 5737）** —— 保证不可路由、不回应 ⇒
  真去连会阻塞在 **SYN 重传（Linux `tcp_syn_retries=6` ≈ 127 秒）**。
- 对照地址选**会被快速拒绝或立即返回**的（已关闭端口 / 正常类名）。

**本目标实测（fastjson `@type` 是否被当 URL）：**

| 载荷 | 耗时 |
|---|---|
| 基线 `{"@type":"zzz.Probe"}`（无 URL） | **4180ms**（★ 抖到 4 秒） |
| `http:..<IPINT>:<记录端口>.probe` | 1881ms |
| **`http:..<192.0.2.1 的整数形式>:80.probe`** | ★★ **301ms** |
| `jar:http:..<192.0.2.1 整数形式>:80.probe!.P` | ★ **323ms** |

⇒ **指向"必卡"地址反而最快 ⇒ 没有发起任何 TCP 连接** ⇒ classloader 不把资源名当 URL 解析
⇒ 不是 Spring Boot fat-jar（CVE-2026-16723 唯一前置不成立）。

**★★ 两条必须记住的纪律：**

1. **目标端点的响应时间抖动可能极大** —— 本端点首次只测了 4 发（301ms ~ 4180ms，约 13 倍），偶发到 **31.8 秒**。
   ⇒ **单发的时间差（几百毫秒）毫无判别力**；只有"数十秒 vs 数百毫秒"这种**量级差**才可信。
   ★ **2026-09-24 晚修正（这条原写"不适合做时间盲注"，过宽，两处改）**：
   同日做了 **24 发规范测量**（两组等价无害探针各 12 发，间隔 4s），真实分布是
   **A 组 `min=189 / p50=284 / p90=586 / max=1265 ms`（max/min=6.7x，p90/p50=2.06x）**、
   **B 组 `190 / 278 / 436 / 799 ms`**；**两组中位数差仅 6 ms**、**噪声带宽 1075 ms**。
   ⇒ 准确结论应分两层：
   - **毫秒级（含"毫秒级延迟"型盲注）差分不可用** —— 信号 ≈ 6ms、噪声 ≈ 1075ms，**噪声是信号的 ~179 倍**；
     要捞出 6ms 需**数千次采样**（= 批量本身）。
   - ★ **但"不适合做时间盲注"这句不能要**：`SLEEP(n)` 的**秒级延时比噪声带宽大、是可分辨的**。
     挡它的**不是**"端点抖动"，而是它**属资源消耗型手法**（一个 20 表库的盲注 ≈ 11,200 次请求 × `SLEEP(5)`
     ≈ **15.6 小时持续阻塞数据库**，且每发占一个工作线程 ⇒ 连接池被吃满）⇒ **落 DoS 绝对红线**。
   ⇒ **教训（通用）：别拿一个"只挡得住弱的"理由，去挡一个"只有纪律才挡得住"的手法。**
     理由用得比它能支撑的更强，被追问一句就塌。**技术结论与纪律结论要分开写、各自说清边界。**
2. **偶发的极端值不要当天启** —— 本轮先看到一发 31.8 秒（差点误判成"连接超时"），
   追查时**同一形态重测只用 1.7 秒**、且**指向必卡地址只用 301ms** ⇒ 证明那只是服务端抖动。
   **规则：任何异常值都要用"对照形态 + 重复测量"解释掉，再写进结论。**
   ★ 且**每轮实验自带阳性对照**（本轮有一轮漏了自测，导致其 History 查询一直空、
   **无法区分"通道没记账"还是"目标没连"**——好在那一轮主结论来自耗时差分，才没被这个疏漏影响）。

⇒ **这两处宽容解析在 1.2.47 到 2.0.65 全区间一致，连 `digits` 表长都没变过 ⇒ 与版本无关。**

★★ **因此「升级到 fastjson2」不能修掉这个 WAF 绕过** —— 它在 fastjson 侧**压根不是安全机制**，是词法层的宽容解析。
**会变的是 WAF 的规则，不是 fastjson 的解析**：问"新版还能不能用"要问 **WAF 规则版本**，不是 fastjson 版本。
（加固含义：要挡这类绕过，只能在 WAF/网关侧对 body 里 `\` 开头的序列做 `\xNN`/`\uNNNN` **归一化或直接拒绝**，
指望升级组件无效。）

**④（公开资料的写法）混合编码**：`\x40\u0074\u0079\u0070\u0065`
（先知社区那位作者实测成功的写法 —— 但**对腾讯云单独用它无效**，见 23.3 #8）

### 23.3 实测矩阵（腾讯云 WAF + fastjson，探针一律**不存在的类名**）

| 键的写法 | WAF | 应用回显 | 结论 |
| --- | --- | --- | --- |
| `"@type"`（明文） | 拦 501 | — | 基线 |
| `"\x40\x74\x79\x70\x65"`（标准 hex） | **拦 501** | — | WAF 会解 hex |
| `"\u0040\u0074\u0079\u0070\u0065"`（标准 unicode） | **拦 501** | — | WAF 会解 unicode |
| ★★ **`"\x4Jtype"`** | **通过** | `autoType is not support. <类名>` | **绕过成立** |
| ★★ **`"\x4_type"`** | **通过** | 同上 | **绕过成立** |
| ★★ **`"\u００４０type"`（全角数字）** | **通过** | 同上 | **绕过成立** |
| ★★ **`"\u๐๐๔๐type"`（泰文数字）** | **通过** | 同上 | **绕过成立** |
| ★★ **`"\u００４０\u0074\u0079\u0070\u0065"`** | **通过** | 同上 | **绕过成立** |
| `"\x40\u0074\u0079\u0070\u0065"`（混合） | 拦 501 | — | ★ 对腾讯云**无效**（与公开资料不同！） |
| `"@type"\r:` / `"\x4Jtype"\r:` | **通过** | `expect ':' at 0, name @type` | 过 WAF（推测按 `\r` 切行），但 fastjson 不接受 `\r` |
| 分块传输拆分 `%40type` | 拦 501 | — | WAF **有分块重组** |

### 23.4 ★★ 判别「autotype 到底开没开」的**无害**方法（⚠️ **本节已被 §24 修正，先读 §24 再看本节**）

> ⚠️ **2026-09-19 纠正**：本节原来把「不存在的类被拒」当作拒绝信号。**那是错的** ——
> fastjson 对**加载不到的类**固定抛 `autoType is not support.`，与 autotype 开关无关。
> **正确探针表见 §24.2**（用 `java.util.Locale`/`java.math.BigDecimal` 判"放行态"、
> 用黑名单成员 `java.lang.Thread` 判"黑名单是否生效"）。下面保留原文仅为记录。

拿到「WAF 放行 + fastjson 消费了 `@type`」之后，**下一问必须是：autotype 是全局禁用，还是只是白名单不含该类？**
不能拿真实 gadget 去试（那是投递可利用载荷）。**用内建无害类型做判别**：

| 探针类 | 回显 | 含义 |
| --- | --- | --- |
| `zzz.nonexistent.Cls9F3A`（不存在） | `autoType is not support. <类名>` | 被拒（正常） |
| **`java.lang.String`** | `can not cast to JSONObject.` | ★ **类型解析通过**（String 被允许，随后因目标类型不符而转换失败） |
| **`java.lang.Integer`** | `parseInt error` | ★ **已进入 Integer 解析** ⇒ 被允许 |

⇒ **`java.lang.String` / `java.lang.Integer` 被放行 ⇒ autotype 机制在工作、并非 safeMode/全局禁用。**
⇒ 拒绝不存在类的原因只是「不在允许范围」。
**这个方法零风险**（内建类型不是 gadget、不联网、不执行代码），却能精确定性 autotype 状态，
**应固定为凭证类/反序列化类目标的标准第二步。**

### 23.5 定性与话说边界（决定报告怎么写）

**能证的**：① 未授权可达 ② WAF 可绕过（≥5 种编码）③ `@type` 抵达 fastjson autotype 判定 ④ autotype 机制在工作。
**不能证的**：某个真实 gadget 能否被实例化 —— **取决于 fastjson 版本 + 白名单/黑名单配置，只能服务端侧确认**。

**★ 报告里绝对不能写的**：「存在 fastjson 反序列化 RCE」。可写的是
「未授权可达的反序列化点 + 外围 WAF 可被绕过（附 5 种编码实证）+ autotype 机制在工作
⇒ **风险等级须上调**，请服务端核查版本/safeMode/名单」。
**「WAF 挡住了」不能作为降低等级的理由 —— 本次已实证可绕。**

### 23.6 处置纪律（与 §20.3 一致，但分界线要划准）

| 允许（手法层） | 禁止（载荷层） |
| --- | --- |
| 各种**编码变形**（`\x`/`\u`/混合/全角/大小写/无引号） | 真实 **gadget 类名**（`JdbcRowSetImpl`/`TemplatesImpl`/BCEL/远程类加载） |
| 位置变形（值/键/query/body/multipart/chunked） | `java.net.Inet4Address` 之类**会触发网络回连**的探测类 |
| 内建无害类型（`java.lang.String`/`Integer`）判 autotype 状态 | `java.lang.Class` 缓存链、`$ref`/`Currency` getter 触发链 |
| 单发、低量 | **延时分块 / 多层编码嵌套 / 大批量触发降级 / 超大数据包填充**（均属 DoS） |

### 23.7 来源（2026 年最新公开资料）

- 先知社区《记一次实战中对 fastjson waf 的绕过》 `xz.aliyun.com/t/15602`
  —— ★ 混合编码写法来源（注意：**对腾讯云单独用无效，须实测**）
- 先知社区《Fastjson1 全版本漏洞利用总结》 `xz.aliyun.com/#/news/92638`
  —— ★ **`\x` 非 hex 第二字符 + `\u` Unicode 数字冒充** 这两条思路的源码级依据
- 博客园《shiro 和 fastjson 漏洞实操总结》 —— `\x40\u0074…` 写法汇总
- CSDN《2026 最新 WAF 分块传输绕过全解析》 —— RFC 模糊地带 / trailer / HTTP/2 分帧（**腾讯云实测分块拆分无效**）
- 博客园《WAF 绕过：从编码变异到协议走私全拆解》 —— 解析差异矩阵、WAF 检测上限表

### 23.8 一句话可复用结论

> **遇到「WAF 拦了 `@type`」时，不要因为「标准 unicode/hex 也被拦」就判定无解。**
> 去查 fastjson 的解码器实现（`digits[]` 表 / `Character.digit`），
> **它的宽容之处就是 WAF 的盲区**：`\x4J`、`\x4_`、`\u００４０`、`\u๐๐๔๐`。
> 判「autotype 开没开」**必须用 §24 的三类探针**（⛔ **别用"不存在的类名"——零信息量**；
> `java.lang.String`/`java.lang.Integer` 被放行只能证明"不是全局禁用"，**不足以判"放行态"**）。

---

## 24. ★★ 修正 §23.4：怎样**正确**判定 fastjson 的 autotype 状态（2026-09-19 亲例纠错）

### 24.1 我犯的错（必须记住）

§23.4 写「用**不存在的类名**当探针，被拒 = 正常，被放行 = 机制在工作」——**这是错的**。

fastjson 源码：`checkAutoType` 里 **`TypeUtils.loadClass()` 返回 null（类根本加载不到）就抛
`autoType is not support. <类名>`** —— **与 autotype 开关无关**。
⇒ **拿"不存在的类"当探针，永远得到同一句，零信息量**。亲例：我据此推断过"autotype 关着"，**判反了**。

### 24.2 正确的探针设计（三类都要用）

| 探针类 | 关键特性 | 响应 | 判读 |
| --- | --- | --- | --- |
| `zzz.nonexistent.Cls9F3A` | **加载不到** | `autoType is not support. zzz…` | ⚠️ **无信息**（加载失败的固定文案） |
| ~~**`java.util.Locale`** / **`java.math.BigDecimal`**~~ | **存在** · 无常用无参构造 · **非 gadget** | **`create instance error`** | ⛔ **不能用来判"放行态"！见下方 ⚠️（2026-09-20 修正）** |
| **`java.lang.Thread`** | **存在** · 且在 fastjson **内置黑名单** | **`autoType is not support. java.lang.Thread`** | ⛔ **也不能单独当"黑名单在生效"的证据！见 §24.3.3** |
| `java.lang.Class` + `val:"java.lang.String"` | 存在的类 | `can not cast to JSONObject.` | ★ `@type=Class` 分支**被执行**，`val` 被真实加载 |

### 24.3 判读矩阵

| 现象组合 | 结论 |
| --- | --- |
| Locale → `create instance error` **且** Thread → **被拒** | ★★ **autotype 放行态 + 仅内置黑名单兜底**（= 最危险配置，亲例即此） |
| Locale → **被拒** | autotype 收窄（有自定义 `accept` 白名单，或 autoTypeSupport=false 且未放行 `java.util.`） |
| 出现 **`safeMode not support autoType : <类名>`** | ★ **这是 safeMode 开着的唯一明确文案** |

★ 精确化：**没见到 `safeMode not support autoType` 就不能说 safeMode 开着**。
（§23.4 那句"未见 safeMode 文案 ⇒ 疑似未开"方向对，但当时拿错了支撑证据。）

### 24.3.1 ⚠️⚠️ 重大修正：**`Locale` 类探针是错的 —— 它们走的是 `mappings` 内建分支**

**2026-09-20 实测后修正。** 上面 §24.2 把 `java.util.Locale` / `BigDecimal` 当"放行态"探针 —— **这个设计有洞**：

- fastjson 的 `checkAutoType` **第一步就是查 `TypeUtils` 的映射缓存**（`getClassFromMapping`），
  **命中即直接返回，白名单/黑名单全都不走**；
- 而 `java.util.Locale` / `java.math.BigDecimal` / **`java.net.InetAddress`** / `java.util.UUID` 这类
  都是 fastjson **预注册在 `mappings` 里的内建类**；
- ⇒ 它们返回 `create instance error`，**只说明"内建分支走到了实例化"，跟 autotype 开没开毫无关系**。

**⇒ 判 autotype 状态的正确姿势**：先用**确实存在的、且不在 `mappings` 里的**类当探针 ——
被拒 ⇒ **收窄态**（白名单/黑名单生效）；放行 ⇒ 才谈"放行态"。
拿 `Locale` 判，会把"内置白名单态"误读成"放行态"（我 2026-09-19 就这么判反过一次）。

★ **连带结论（很重要）**：**`java.net.InetAddress` 生效 ≠ "任意类型可控"。**
它走的也是 `mappings` 内建分支 ⇒ 它能被执行，**只证明"内建分支会执行"**，
**不证明"攻击者能投递任意类"**。这两件事中间隔着一道闸（白名单/黑名单），
**别把"执行原语成立"当成"RCE 可达"的充分证据**（报告定级上这是承重墙级别的区分）。

### 24.3.2 判「缓存绕过（CVE-2022-25845 二段路径）」：**本版本机制上不成立**（2026-09-20 源码确证）

CVE-2022-25845 设想的路径是「先经 `Class` 分支把类载入 `mappings`、再二次引用命中缓存跳过闸」。

```
第1步  {"@type":"java.lang.Class","val":"<某个黑名单成员 / 无害类>"}   → 只加载（本意：写缓存）
第2步  {"@type":"<同一个类>"}                                          → 空对象形式
       第2步仍报 autoType is not support.  ⇒ 绕过不成立
       第2步改为业务基线                    ⇒ 绕过成立
```

★★★ **源码查证 ＋ 版本修正（01:05 更正 00:45 的过强表述）**：
`Class` 分支在 **master 分支**是显式 `cache = false`：

```java
// com.alibaba.fastjson.serializer.MiscCodec#deserialze
if (clazz == Class.class) {
    return (T) TypeUtils.loadClass(strVal, parser.getConfig().getDefaultClassLoader(), false);
    //                                                                       ↑ 显式 false
}
// TypeUtils
public static Class<?> loadClass(String className, ClassLoader classLoader) {
    return loadClass(className, classLoader, false);        // 两参数版同样是 false
}
```

**但这是 1.2.48 才改的。** 公开分析一致记载 **1.2.48 从两头堵**：
① `MiscCodec` 的 `cache` 改为 `false`（不再写缓存）；
② `checkAutoType` 把**黑名单检查前移到缓存查询之前**（即使类已在缓存里，也先过黑名单）。

⇒ **正确表述**：该路径 **≤1.2.47 成立（CVE-2017-18349 / CVE-2025-70974）/ ≥1.2.48 被修复**。
**不是"机制上不存在"** —— 00:45 那句下重了、已更正。
⇒ **本目标 4 组实测为负 ⇒ 与「版本 ≥ 1.2.48」一致 —— 这是一条版本判据。**

★ **方法学**：若要判，两步**应在同一条 TCP 长连接内连发**（多后端 LB 下两发会落到不同 JVM、
缓存天然不通；短连接加 sleep 没用 —— 关键是连接）。但**负结果可直接归因为机制**，不必再做 JVM 假设。
★ 仍建议顺手做两步：成本低，且第 1 步能同时复现"类存在性/版本 oracle"。

★ 另注：第 1 步"加载成功"本身**不是漏洞** —— 只是**类存在性/版本 oracle**，
不实例化、不执行逻辑 ⇒ 证明的是"这个名字能被加载"，**不是**"这个类能被投递"。

### 24.3.3 ★★★ **先判闸的类型（白名单 / 黑名单），再谈别的**（2026-09-20 实测后补）

**`autoTypeSupport=false` 时，`checkAutoType` 对"不在内部预注册表里"的类一律抛
`autoType is not support. <类名>`** —— 与它是不是黑名单成员**无关**。

⇒ **后果：白名单态下，所有"黑名单探针"都是零信息量。**
包括 `java.lang.Thread` 那一发：它被拒**可能只是因为它不在内部表里**，
**不能据此说"黑名单在生效"**（§24.2 原来那条判读已被本轮实测推翻）。
⇒ 我 2026-09-19 用 `Thread` / `ThreadLocal` / `XMLChar` 的拒/放行去推**版本区间**，**也因此作废**。

**正确顺序（照这个来）：**

**第 1 步 · 先摸内部预注册表的边界。** 用**纯 JDK 工具类**试 `@type`：
`java.util.ArrayList` / `java.lang.StringBuilder` / `java.util.TreeMap` / `java.util.Locale` …
—— 若这些**放行**，**别以为 autotype 开着**：它们**都在 `ParserConfig.initDeserializers()` 里**
（源码可查：`deserializers.put(ArrayList.class, CollectionCodec.instance)` 等）。

**第 2 步 · 判闸的类型。** 用一个「**内部表里没有、且肯定不是 gadget 的第三方类**」，
先用 `Class`+`val` 确认它**确实存在**，再 `@type` 直投：
- **被拒**（而它确实存在）⇒ ★ **白名单态** ⇒ **deny 名单探针从此一律免做**（做了也是零信息）；
- **放行** ⇒ **黑名单态** ⇒ 此后才可以用 deny 名单探针。
亲例（datashare，2026-09-20；**01:15 修正**）：
先用**顶层** `Class`+`val` 确认"**确实存在（70B）**"（方法见 §24.3.6），再 `@type` 直投：
`org.apache.catalina.startup.Bootstrap`、`org.apache.commons.collections4.Transformer`、
`com.rometools.rome.feed.WireFeed` —— 三者**都存在**、**都不是 gadget**、**都不属任何 deny 前缀**，
`@type` 直投却**一律被拒** ⇒ **白名单态成立**。（若是黑名单态，这三个本应放行。）
★ **原亲例里的 `org.apache.commons.chain.impl.ChainBase` 已剔除** ——
用有效形式重测为 **43B ⇒ 类路径上不存在**，它的"被拒"属**零信息量**（原因见 §24.3.6）。

★ **一句话**：**判"被拒"之前，先问"它本来该不该被放行"。**
拿内部表里的类去测，是拿白名单当 autotype 判据；拿白名单态下的"被拒"去推黑名单，是双重错。

### 24.3.4 ★★ 「阳性对照」的分工：判 `safeMode` 与判 autotype 要用**两组不同**的类
（2026-09-20 查 `checkAutoType` 源码 + 实测后补）

`checkAutoType` 的实际顺序（源码要点）：

```
① autoTypeCheckHandlers（外部注册的 handler，如 dubbo）
② if (safeMode) throw "safeMode not support autoType : <类名>"     ← ★ 在任何查表之前
   ... 哈希计算 / internalDenyHashCodes ...
③ clazz = TypeUtils.getClassFromMapping(typeName)                  ← 内建表，命中即 return
   if (clazz == null) clazz = deserializers.findClass(typeName)
④ if (!autoTypeSupport) { ...deny/accept...; throw "autoType is not support. <类名>" }
```

⇒ **两组探针，各判一件事，缺一组画像就不完整：**

| 组 | 用什么类 | 判什么 | 机制 |
|---|---|---|---|
| **A 阳性对照** | **内建表内的纯 JDK 类**：`java.util.ArrayList` / `java.lang.StringBuilder` / `java.util.TreeMap` | **排除 `safeMode`** ＋ 证明**解析链路活着、真在构造对象** | ② 在 ③ 之前 ⇒ 内建类能实例化 ⇒ safeMode 必为 false |
| **B 判别器** | **内建表外、非 gadget 的第三方类**：`org.apache.commons.chain.impl.ChainBase` / `org.apache.catalina.startup.Bootstrap` | **判 `autoTypeSupport=false`** | 不命中 ③ ⇒ 走到 ④ 的 `throw` |

- **只做 A** ⇒ 把白名单态误读成"放行态"（§24.3.1 + 2026-09-20 各犯一次，同一根因）。
- **只做 B** ⇒ **无法排除 `safeMode`**：safeMode 下 A 组**同样会被拒**，两组"全拒"时分不清是哪一种收窄；
  且没有 A 组的"放行"作基线，B 组的"被拒"**不可解读**（分不清被闸拒 / 链路坏 / WAF 拦）。
- ★ **两个文案要分开记**：`safeMode not support autoType : X`（safeMode）vs `autoType is not support. X`（闸/名单）。

★ **别把「白名单态成立」读成「不可利用」**：白名单态下 `checkAutoType` 仍有多条会让 `loadClass` 发生的路径
（`internalWhite` 框架内置白名单 / `jsonType`（类带 `@JSONType` 注解）/ 外部 `autoTypeCheckHandler` / `expectClass` 分支）。
公开源码事实 —— **"收窄"不等于"关闭"**。展开构造不在本知识库范围。

### 24.3.5 ★★★ **「测量即污染」：白名单态下剩下的那条通路，不可由外部试**
（2026-09-20 验证 `TypeUtils.loadClass` 源码后补）

**白名单态下，能让外部指定的类名通过的路径清单**（源码 `checkAutoType`）：

| # | 通路 | 触发条件 | 属谁的资源 |
|---|---|---|---|
| 1 | `internalWhite`（`INTERNAL_WHITELIST_HASHCODES`） | framework 自带的类 | fastjson 自己，不是通用载体 |
| 2 | **`acceptHashCodes`**（应用配的 accept） | `addAccept` 配过 | ★ **甲方内部信息** |
| 3 | **`jsonType`** | 类上带 `@JSONType` 注解 | ★ **依赖类路径 —— 甲方内部信息** |
| 4 | `autoTypeCheckHandler` | 框架注册（dubbo 一类） | ★ **甲方内部信息** |
| 5 | `expectClassFlag` | 应用有具体类型字段（`expectClass != null`） | 窄，且随后有 `isAssignableFrom` 校验兜住 |

★★ **而第 3 条有一个致命性质 —— 它不能被"试着测"：**

```java
// ParserConfig.checkAutoType
if (autoTypeSupport || jsonType || expectClassFlag) {
    boolean cacheClass = autoTypeSupport || jsonType;      // ★ jsonType=true ⇒ cacheClass=true
    clazz = TypeUtils.loadClass(typeName, defaultClassLoader, cacheClass);
}
```

```java
// TypeUtils.loadClass(String className, ClassLoader classLoader, boolean cache)
if (cache) { mappings.put(className, clazz); }   // 三处分支各一次
private static ConcurrentMap<String, Class<?>> mappings = new ConcurrentHashMap<>(256, 0.75f, 1);
```

⇒ **`jsonType` 命中 ⇒ 该类的 类名→Class 映射被写进 `TypeUtils.mappings`**
—— 一个**静态** `ConcurrentHashMap`，**JVM 生命周期内不会自行清除**（只有显式 `clearClassMapping()` 能清）。

⇒ ★★ **结论：这条通路的"试探"与"状态改变"不可分离。**
试成功一次 = **在一个本该被白名单拒绝的类上，永久写入全局类映射**。
⇒ **该通路不可由外部无副作用地测量** —— 只能甲方自查（一笔 `grep` 就能回答）。

★ **方法论（可复用）**：判"某条链能不能由我外部试"时，除了"有没有先攻破一道安全机制"，
再加一问：**「这条通路的探针，是不是就是载荷？成功之后会不会改变目标的全局状态？」**
若"是 + 会" ⇒ **测量即污染 ⇒ 不可外部试**，无论授权多充分。
（与 §27「有状态绕过 + 残留不可清」同源，但此处更强：**污染正是"成功"的充要后果**，不是绕过的副作用。）

★ 对照：第 2 条（accept）命中同样会 `loadClass(cache=true)`，但写进去的是**应用本来就授权的类**
⇒ 那不算污染，属既有配置的既有行为。

★★ **写进去之后到底意味着什么 —— 后果链（逐层）**：

1. **该类型名从此"免检"。** `checkAutoType` 中 `clazz = TypeUtils.getClassFromMapping(typeName)`
   命中后**直接 `return clazz`** —— 这个位置在 `autoTypeSupport` 分支、deny/accept 遍历、
   以及 `ClassLoader` / `javax.sql.DataSource` / `javax.sql.RowSet` 三道硬拦**之前**
   （唯一仍排在它前面的是 `safeMode`）。
   ⇒ **后续任何请求写同一个类名，都不需要任何绕过构造即可通过。**
   （唯一例外：该处解析若带 `expectClass` 字段类型约束，仍会过一次 `isAssignableFrom`。
   但 `param` 已实测是 Map/JSONObject 泛型落地 ⇒ **无此约束，完全免检成立**。）
2. **影响半径 ＝ 同一份 fastjson 类（同一 ClassLoader）下的所有使用点。**
   `TypeUtils.mappings` 是 `TypeUtils` 的**类级静态字段**，同 ClassLoader 内共享。
   常见形态：该应用**全部** fastjson 调用点一并受影响，**不限于被打的那个接口**；
   若 fastjson 装在容器共享 lib（如外置 Tomcat 的 `lib/`），则**同容器内其它应用一并受影响**。
3. **不可逆。** 只能靠 `clearClassMapping()` 清除（应用不会主动调）
   ⇒ **恢复的唯一方式是重启 JVM**；而重启生产服务＝业务中断＋变更流程，且**只能由甲方执行**。
4. **不可见。** 内存态，重启即消失 ⇒ 甲方大概率**不会知道发生过**。
   但对研究者而言，性质已从「只读探测」变为「**改写生产系统的运行态**」。
5. ★★ **最要紧的一条**：若写进去的正是**可用作利用链载体的类**
   （而"找一个能用的类"正是试探的目的），这次试探就等于**把钥匙留在门上** ——
   **它把"需要复杂构造才能达成一次"的一次性状态，变成了"长期、零成本、对所有人可重复利用"的状态。**

⇒ ★★ **这条链的「成功」与「代价」是同一个动作。**
不是"留了痕迹"，而是"**为了证明门能开，先把门卸了 —— 而卸下来就一直开着**"。
**因此该通路不可由外部试，与授权是否充分无关。**

### 24.3.5.1 `Class` + `val` 存在性 oracle：干净，但有一条分支纪律

`Class` + `val` 是**不写缓存、不实例化**的类存在性 oracle（`cache = false` 已源码确证，见 §24.3.2）——
它是"**零副作用读类路径**"的主力工具。

★ **但"无害"有一个条件** —— `TypeUtils.loadClass` 内部三条分支，**副作用不同**：

```java
if (classLoader != null) {
    clazz = classLoader.loadClass(className);  ...        // ① 不触发 <clinit>
}
ClassLoader ctx = Thread.currentThread().getContextClassLoader();
if (ctx != null && ctx != classLoader) {
    clazz = ctx.loadClass(className);  ...                // ② 不触发 <clinit>
}
clazz = Class.forName(className);                         // ③ ★ initialize=true ⇒ 执行 <clinit>！
```

- ①② 用 `ClassLoader.loadClass` ⇒ **不初始化**，干净；
- ③ 用 `Class.forName`（默认 `initialize = true`）⇒ **会执行目标类的静态初始化块**。

**常见容器环境**走 ②（context CL 非 null 且 ≠ `defaultClassLoader`）⇒ 干净。
**但若 `defaultClassLoader` 被设成与 context CL 同一个** ⇒ 落到 ③。

⇒ ★ **纪律：拿 `Class` + `val` 做存在性探测时，只选"静态块无副作用"的类。**
JDK 标准类通常安全；**第三方类要当心** —— 有的 `<clinit>` 会读配置、起线程、连数据源（那是**真副作用**）。
选探针的顺序：**JDK 标准类 > 已确认无静态块的工具类 > 其它**。别拿陌生的第三方类当存在性探针。

### 24.3.6 ★★★ 黑盒判定 fastjson：**oracle 必须先自证「两档可分」**（2026-09-20 实测）

**核心纪律**：**任何 oracle，先用「必然存在」与「必然不存在」两个已知端点各打一发，
确认两档返回**可分**，才敢用它判第三发。**
—— 否则你拿到的是**零信息量**，而**零信息量长得像成功**。

亲例（datashare，2026-09-20）：**同一个 `Class` + `val`，换个位置放，判别力完全不同**

| 形式 | 载荷 | 存在 | 不存在 | 判别力 |
|---|---|---|---|---|
| **顶层** | `{"@type":"java.lang.Class","val":"X"}` | **70B** `can not cast to JSONObject.` | **43B** `""` | ★ **有效** |
| **嵌套** | `{"z":{"@type":"java.lang.Class","val":"X"}}` | **79B** 业务基线 | **79B** 业务基线 | ✘ **零信息** |

原因：嵌套时整体解析成 **Map**，内层 `loadClass` 返回 null 只是"某字段为空"，不影响外层类型
⇒ 业务照常继续 ⇒ 两种情形**逐字节相同**。顶层时整体就是那个 `Class` 对象（或 null）
⇒ 类存在则业务 `(JSONObject)` 转换失败（70B）、不存在则为空（43B）。

⇒ ★ 我们此前用**嵌套形式**做过一批"类存在性确认"，**全部作废**（当时被读成"存在/放行"，
`verdict` 甚至写成「★★ 放行（实例化成功）」—— 而 `Class` 分支**根本不实例化**，判读词本身就错）。
⇒ 用有效形式重测的结果见 §24.3.4 亲例。

**白名单态下，`Class` + `val`（顶层形式）是唯一还能读「类路径 / 版本」的黑盒手段** ——
因为 `@type` 为 `java.lang.Class` 时命中**内建表**即返回，走 `MiscCodec`，
**完全绕过 `checkAutoType`**，不受白名单态影响。

**版本标志类（黑盒可测，顶层形式；存在=70B / 不存在=43B）**

| 类 | 引入版本 | 判读 |
|---|---|---|
| `com.alibaba.fastjson.support.geo.Feature` / `Geometry` | **1.2.68** | 存在 ⇒ **≥1.2.68** |
| `java.lang.Module` | JDK9+ | 不存在 ⇒ JDK 8 |

**★ 但公开的那些「版本探测手法」在白名单态下大多失效**，别照搬：

| 公开手法 | 白名单态下 |
|---|---|
| `AutoCloseable` 精确探测 / 黑名单成员拒或放行 | ✘ **零信息** —— 非内建类一律被拒，与版本无关（§24.3.3） |
| `geo.Feature` 之类版本标志类 + `Class` oracle | ✔ **有效**（绕过 checkAutoType） |
| 报错文案差异 | ⚠ 取决于应用是否回显解析器 message |
| 依赖/类路径探测（Character 报错、`Class` MiscCodec） | ✔ 有效（同样绕过 checkAutoType） |
| ~~1.2.36–1.2.62 的 DoS 型版本探测~~ | ⛔ **禁止**（DoS 绝对红线） |

### 24.3.7 ★★ 「加载」「执行」「执行我们提供的代码」是三层，别混
（2026-09-20 补；与 §24.3.1 的「执行原语已证 ≠ 任意类型可控」是一对）

黑盒里最容易被"无害类"带偏的推理链：

| 层 | 含义 | 用无害类能证吗 | 够不够 RCE |
|---|---|---|---|
| **L-a 加载** | 服务端把该**类名** `loadClass` 进 JVM | ✔ **能**（`Class`+`val` 顶层形式） | ✗ |
| **L-b 执行** | 该类被实例化 / `<clinit>` 跑起来 | ⚠ 部分（内建表类可实例化，但那是"服务端本来就授权的类"） | ✗ |
| **L-c 执行我们提供的代码** | **我们给的字节码**被 `defineClass` 并运行 | ✗ **不可能** | ✔ **这才是 RCE** |

★ **L-c 在定义上不可能"非恶意"**：**载荷的内容就是代码 —— 你不可能"让目标执行你的代码"却不提供代码。**
（`TemplatesImpl._bytecodes` / BCEL 串 / 远程类，三者的区别只是"代码怎么送进去"，**都得送代码**。）

★ **L-a 的极限（我们已达）**："无害类"能回答的只有两件事 ——
- **闸的状态**：内建表**内**的类放行 ⇒ 判 `safeMode`；内建表**外**且**已证存在**的类被拒 ⇒ 判白名单态；
- **类路径有什么**：`Class`+`val` 读版本标志类 / 依赖类 ⇒ 判版本、JDK、gadget 库存在性。

⇒ **它回答不了「能否执行我们的代码」** —— 那一环在闸的另一侧。

★ **一条相关死角（存在，但不必测）**：`TypeUtils.loadClass` 的第三条分支是
`clazz = Class.forName(className)`（默认 `initialize = true` ⇒ **会跑目标类的 `<clinit>`**）。
若某环境落到该分支，`Class`+`val` 就从"加载"升级为"执行原语"。**但**：
① 常见容器走第二条（`ctx.loadClass`，**不初始化**）；
② **即使走到了，执行的也是那个类自己的代码，不是我们的**；
③ 要用它做 RCE，需要一个"`<clinit>` 有危害副作用"的现成类 ⇒ **那就是 gadget（找载具），不在产出范围**。
⇒ 记为「**未测定 ＋ 为什么不必测**」，而不是"待验证"。

### 24.3.8 ★★ 「版本链」与「白名单态」是两个独立维度，别拿前者的思路找后者
（2026-09-20 补）

白名单态下，"针对某个版本的 bypass"几乎都用不上 —— 因为两者的**作用点不同**：

| 维度 | 解决什么 | 作用位置（`checkAutoType`） |
|---|---|---|
| **版本链**（`AutoCloseable` 作 expectClass / `Throwable` 子类嵌套 `@type` / 各类"需 AutoType enable"的链） | 绕**名单**、或绕**特定版本的判断缺陷** | 多在"**类名已进入检查范围**"之后 |
| **白名单态**（`autoTypeSupport = false`） | **非内建表类一律不放行** | **方法末段的 `throw`** |

⇒ **白名单态的位置更靠后、覆盖面更大** ⇒ 版本链的前置（"类名能进入检查范围"）**先就不成立**。

**逐条对照**：

| 版本链 | 前置条件 | 本目标（实测前提） |
|---|---|---|
| `AutoCloseable` 作 `expectClass`（≤1.2.67） | `expectClass != null`（应用有**具体类型字段**） | ✘ 已实测**无位置闸** ⇒ `expectClass = null` |
| `Throwable` 子类嵌套 `@type`（≤1.2.79） | `@type` 指向 Throwable 子类 | ✘ 非内建表 ⇒ 末段 `throw`（源码另有 `Throwable.class.isAssignableFrom(clazz) ⇒ clazz = null` 专治） |
| 1.2.48 – 1.2.67 的各类链 | `autoTypeSupport = true` | ✘ 实测 `false` |
| **`@JSONType` 通路（1.2.80+；1.2.83 有公开分析）** | **类路径上存在带 `@JSONType` 注解、且可作载体的类** | ⚠ **唯一可能活的 —— 但前提是内部信息** |

★ **⇒ 结论：在"高版本 ＋ 白名单态"下，唯一还活的是 `jsonType` 通路。**
它不靠"版本技巧"，靠"**类路径上恰好有一个带 `@JSONType` 的可用载体**"。
而那正是"通路的危险系数"那一类**内部信息**（见 §24.3.5 / §24.3.6）。

★ **推论（找料时的省事准则）**：当目标已确证为白名单态时，
**不必再去找"某个版本的 bypass"** —— 先问"**这类名能不能过闸**"。
过不了闸，版本链再巧也是在门外面比划。

### 24.3.9 ★★ 「accept 名单」是**可测的**（前缀维度）—— 我曾误判为"外部不可测"
（2026-09-20 实测后补；**纠正 §24.3.5 表格里「① accept 名单：外部零信号」的表述**）

**原理**：白名单态分支里，accept 的匹配是**逐字符累积 hash、每步检查**：

```java
if (!autoTypeSupport) {
    long hash = h3;
    for (int i = 3; i < className.length(); ++i) {
        char c = className.charAt(i);
        hash ^= c; hash *= fnv1a_64_magic_prime;
        if (Arrays.binarySearch(denyHashCodes, hash) >= 0) { ...throw... }
        if (Arrays.binarySearch(acceptHashCodes, hash) >= 0) {
            clazz = TypeUtils.loadClass(typeName, defaultClassLoader, true);
            if (clazz == null) {
                return expectClass;      // ★ 命中名单但**类不存在** ⇒ 不抛异常
            }
            ...
        }
    }
}
...
if (!autoTypeSupport) throw new JSONException("autoType is not support. " + typeName);
```

⇒ **投「某前缀 ＋ 一个必然不存在的类名」：**
- **命中名单** ⇒ `loadClass` 失败 ⇒ `return null` ⇒ **响应不再是 `autoType is not support.`**
- **未命中** ⇒ 走末段 ⇒ **`autoType is not support. <类名>`**

★ **无害性**：类名不存在 ⇒ 无实例化、无 `<clinit>`；`loadClass` 失败 ⇒ **不写 `mappings`**（**零污染**）。

★★ **关键推论**：因为匹配是**逐字符累积**，所以
**「`com.` 未命中」⇒ 名单里不含任何以 `com.` 开头的前缀**（`com.lexin.` 等是其子集，自动排除）。
**一个宽前缀的负结果，能关掉一整个命名空间** —— 这是本判据的效力所在。

**亲例（datashare，2026-09-20）** —— 共 16 个前缀，**全部未命中**：

| 批次 | 前缀 |
|---|---|
| 一 | `com.` · `com.lexin.` · `com.fenqile.` · `com.lexinfintech.` · `com.lexincloud.` · `cn.lexin.` · `org.apache.` · `com.alibaba.` |
| 二 | `io.` · `net.` · `org.` · `org.lexin.` · `lexin.` ＋ 2 个基线形态 |

⇒ **四个顶级宽前缀（`com.` / `io.` / `net.` / `org.`）全部负 ⇒ 覆盖了绝大多数 Java 类名空间。**
（脚本：`probe_accept_prefix.py` / `probe_accept_prefix2.py`）

★ **但仍有两个残余，别写成"名单为空"**：
1. accept 也可以配**完整类名**（而非前缀）⇒ **本测法测不到**（匹配要 hash 累积到那个长度才命中）；
2. 非主流前缀未穷举（如 `cn.` 本身、单段包名等）。
⇒ 结论只能写「**已排除这些前缀**」，不能写「名单为空」。

### 24.3.10 ★★ 「目标上有没有带 `@JSONType` 的类」—— **可以零污染地判一半**
（2026-09-20 实测后补）

`jsonType` 通路的机制前提 = 「类路径上存在带 `@JSONType` 注解的类」。
**这一半能确认，方法是两条公开信息相加**：

1. **"某类带不带 `@JSONType`"是公开事实** —— 注解（RUNTIME retention）写在类文件里，
   查框架/库的源码即可知（GitHub raw 直接看，无需任何探测）；
2. **"该类在不在目标类路径上"** ⇒ 用 **`Class` + `val`（顶层形式）零污染**验证
   （`cache = false`，见 §24.3.2 / §24.3.5.1）。

**亲例（datashare，2026-09-20）**：
- **源码**：`com.alibaba.fastjson.support.geo.Feature`
  `@JSONType(typeName = "Feature", orders = {…})`；
  `com.alibaba.fastjson.support.geo.Geometry`
  `@JSONType(seeAlso = {…9 个子类…}, typeKey = "type")`；两者 `@since 1.2.68`。
- **实测**：两者在目标类路径上**均存在**（`Class` oracle，70B）。
⇒ ★ **结论：目标上确实存在带 `@JSONType` 的类 ⇒ `jsonType` 通路的机制前提成立。**

★★ **但"有带注解的类" ≠ "有可用的载体"**：
geo 族（`Geometry` / `Feature` / `Point` / `Polygon` …）**全是普通 DTO**
（字段 ＋ getter/setter），反序列化它们 = 构造一个普通对象 ⇒ **零危害**。
⇒ **还缺"一个同时是反序列化 gadget 的 `@JSONType` 类"** —— 这是**双条件交集**，
**稀缺**（CVE-2022-25845 那类 PoC 之所以罕见，原因正在此），
且**它是否在目标类路径上属内部信息**。
⇒ **找那个类 = 找载具（不做）**；"能不能用"仍只能由内部回答。

★ **这条对报告的用处**：它把"通路 ②"从"完全未知"推进到
「**机制前提已确认成立，只差载具**」—— 所以"请核查依赖清单"这个诉求**变得更强、更具体**。

### 24.3.11 ★★ 「TCP 出站」为什么测不了 —— 能过闸的不发连接，发连接的过不了闸
（2026-09-20 实测后补）

白名单态下，想测"目标能不能**主动发起 TCP 连接**"（连到自有 Listener），会撞上一个**交叉缺口**：

| 载体 | 过 `checkAutoType`？ | 发起 TCP？ |
|---|---|---|
| `java.net.URL` / `InetAddress` / `InetSocketAddress` / `File` / `URI` / `Charset`（内建表） | ✓ | ✗（`new URL(str)` **只构造对象**；`InetAddress` **只做 DNS**） |
| 带 `@JSONType` 的普通 DTO（如 `com.alibaba.fastjson.support.geo.*`） | ✓ | ✗ |
| JNDI 载体（`JdbcRowSetImpl` 等） | ✗ | ✓ |
| 字节码载体（`TemplatesImpl` / BCEL） | ✗ | ✓（间接） |

⇒ ★ **两个集合无交集**。**"能过闸的"都不发连接，"发连接的"都过不了闸。**

⇒ **所以 TCP 出站无法用"无害探针"测** —— 这不是"还没找到方法"，
而是**这个测试本身就需要一个能建连接的载荷**，而载荷按定义属于"投递"。

★★ **关键认知**：「测 TCP 出站」与「能不能 RCE」**共用同一个前置**（能让外部类名过闸）。
⇒ **不必单独测；一旦前置成立，这一步顺带就答了**（例如 JNDI 链本身就走 TCP）。

★ **别踩的坑**：某次 PoC 打出去「无回显 / 无回连」，**不能**直接读成「出网被挡」——
先确认那次 PoC **有没有走到需要出网的步骤**。
（亲例：某公开 PoC 要 Spring Boot `LaunchedURLClassLoader`，而本目标实测**没有**
⇒ 那次"没反应"**对 TCP 出站零信息量**，它死在更早的前置上。）

### 24.4 安全边界（三条探针都无害，但要守）

- `Locale` / `BigDecimal` = JDK 值类，构造后只持有字符串/数值，无文件/网络/命令副作用
- **`java.lang.Thread` 必须用"空对象"形式**（`{"@type":"java.lang.Thread"}`，**不给 `target`/`Runnable`**）
  ⇒ 不调 `start()` ⇒ 什么也不运行。同理 `ProcessBuilder` 不给 `command` 就不会起进程
- **⛔ 判出"放行态"之后，不要顺势投一个 `JdbcRowSetImpl` 去"闭环"** —— 那已经是**实际攻击投递**，
  不是验证。**边界线画在"载荷能否执行"上，不画在"手法像不像攻击"上。**
  ★ **2026-09-19 口径**（全文见 §25.1）：上句针对 **② 类**（投真实 gadget / 需先绕安全机制）；
  **① 类"只读最小命令证明"（`id` / `whoami`，单发只读非破坏）授权范围内全部环境可做**，非生产实例 / 本地靶场
  更是可投 `lab.DemoGadget` 一类或跑全套链（乐信 lab 已实证，见 `lab/证据记录.md`）。

### 24.5 定级含义

「**autotype 放行态 + 只有内置黑名单兜底**」⇒ **风险等级必须跳到最高档**：
三个前提（① 未授权可达 ② WAF 可绕 ③ autotype 放行）**全部可实证**，
唯一未证的是"类路径上存在黑名单外的可用 gadget"——**那是甲方内部信息，攻击者无法从外部排他证明，
因此不能因为"未证"而降级**。报告写法：
「未授权可达 + WAF 可绕 + autotype 处于放行态（附三类探针实证）⇒ 严重风险，须服务端核查版本/配置/依赖清单」。

### 24.6 顺带：WAF 对本类目标的附加规则

亲例中 `java.lang.ProcessBuilder` 被 **501 WAF 拦**，而 `java.lang.Thread` 到了应用层 ⇒
**WAF 除了 `@type` 规则外，另有"危险类名"关键字规则（覆盖不完整）**。
⇒ 探测序列里若某类被 501 拦，**换同类但名字不敏感的探针**（如用 `Thread` 而不是 `ProcessBuilder`）再判。

★ **2026-09-19 乐信 datashare 追加**：同一台目标上，
`com.sun.org.apache.xalan.internal.xsltc.trax.TemplatesImpl` 被该关键字规则**拦**（501 + 693B 拦截页），
而 `com.sun.rowset.JdbcRowSetImpl` **没被拦**（到达应用层，回 `autoType is not support.`）。
⇒ **同一个 WAF 对不同载体类的规则是不同的，覆盖确实不完整。**

★★ **由此得到一条判读纪律**：
**被 WAF 拦的那一发，不能拿来当"后端 deny 名单"的证据 —— 层级不同。**
"WAF 拦了" 只说明"请求没到应用层"，**名单答案仍未测定**（且 §2 明确：WAF 挡住不作降级理由）。
报告里要写"**未测定 + 为什么没继续**"，不能写"被拦 = 不可利用"。

### 24.7 ★★★ 「名单覆盖了某个类名」**≠**「那个载体不可用」（2026-09-19 亲手踩的坑）

我在 datashare 上先推出「版本 ∈ 1.2.25–1.2.41」，然后写下了**「四个主载体全被前缀覆盖 ⇒ 本条链不可利用」**。
**这个结论是错的，当晚撤回。** 错因一句话：

> **判据所用的字符串，与实际加载时所用的字符串，可以不是同一个。**
> 我却拿"名单里的条目能匹配这些**类名**"去等价"这些**载体**不可用"。

- **1.2.25–1.2.41 的名单是「明文前缀数组」，匹配方式是 `className.startsWith(denyList[i])`**
  （独立来源证实；1.2.42 改为 `denyHashCodes` + `fnv1a_64`）。
- 而在这一段区间，**校验用的名字与加载用的名字在实现里经过了不同的处理**
  ⇒ 两者不一致时，校验可以"看不见"真正会被加载的那个类 —— 即**存在单字段级别的绕过口**（1.2.42 才修）。

★ **可复用的警惕线**：凡是「**先按 A 的形态做判断，再按 B 的形态去执行**」的实现，
都要多问一句：**A 与 B 是不是同一个字符串？** 典型场景：类型/类名/路径/文件名/域名的**规范化与校验分离**、
大小写、前后缀、编码、`L…;` 这类描述符包装。
**名单的"覆盖"只是"匹配"，不等于"拦截"。**

★ **带来的立场变化要说清楚**：以前是"链本身不通所以不谈"，
现在变成"**链能通，而我不产出那一步所需的东西**"——后者**更不舒服，但要如实讲**。

---

## 25. ★★ RCE / 命令执行类目标：**「验证天花板」在哪里**，以及不打生产也能定论的三条路
> 2026-09-19 乐信 datashare 定案。适用于任何「反序列化 / 表达式注入 / 模板注入 / 上传」类目标。

### 25.1 先分清「验证」与「利用」——分档两条

> 判据仍是：**载荷能否执行代码（或产生无法事前评估的副作用）？**
> ★ 2026-09-19 用户定调后，**边界改画在两处：有没有必须先攻破的安全机制 × 副作用能不能事前算清**。

| ① 属于「验证」（**可做，含生产**） | ② 属于「利用」（**可做，含生产**但是要提前告知用户危害，用户需要同意） |
|---|---|
| 编码变形、位置变形、大小写、转义（**手法随便试**） | **让目标加载远程类**（LDAP/RMI 下发 reference / class）、返回可反序列化对象 |
| 用**不存在**的类名 / **内建无害类**判 autotype 状态 | **必须先攻破一道安全机制才能投递的链**（fastjson 黑名单绕过是典型） |
| 用**黑名单成员的空对象**判黑名单是否生效（`{"@type":"java.lang.Thread"}`，不 start） | 第二段执行载荷 / 起常驻进程 / 写文件 / 改配置 |
| 读报错文案、指纹、配置探测 | |
| **只读最小命令证明**（`id` / `whoami` / 无害标记串） | |
| **仅解析 / 无载荷回连**：DNS 型 OOB（`Inet4Address`、`dnslog` 域名一类）或**空响应 Listener**（只记录连接，**不返回任何 class / 可反序列化对象**） | |

★ **边界线不画在"手法像不像攻击"上，也不画在命令字面量上，而是画在这两条上**：
**有没有必须先攻破的安全机制** + **副作用能不能事前算清** —— 它决定这一发属 ① 还是 ②。
★ 属 ② 的：**既不写死禁止，也不由我单方拍板** —— **先向用户说明后果，由用户决定做不做**（见下）。
★ **前置绝对约束：DoS 红线优先于本档** —— 若载荷副作用含「打崩服务 / 资源耗尽」⇒ **不做，用户同意也不做**
  （2026-09-19 用户确认「不能 dos 攻击，会导致系统崩溃」）。本档只放行「让目标执行代码」，不放行「让服务不可用」。

★ **2026-09-19 用户定调（与 `SKILL.md §2` 第 9 条一致）**：
· **①** ⇒ **授权范围内全部环境可做，含生产**。纪律：**单发、低量、只读 / 无副作用、不落文件、不覆盖、不删改、不批量**；
  **先跑无害标记确认点真被消费，再上真值**；**OOB 用每次唯一域名、不轮询，优先自有 / 平台提供的 OOB**
  （public `dnslog.cn` 会把目标出口 IP 暴露给第三方，金融目标尽量避开；用户自己发的记录可查、不重复发）。
· **② 执行型载荷（含让目标执行我们提供的代码）：先向用户描述后果，取得用户明确同意后执行** ——
  描述四项：**① 载荷是什么**（投什么、怎么投）· **② 在目标上会发生什么**（哪一段被触发、执行到哪一步）·
  **③ 副作用与影响面**（能否事前算清、blast radius、是否影响生产业务）· **④ 中止与善后方式**（怎么停、怎么清）。
  —— **未取得用户明确同意 ⇒ 不做**，走 §25.3 路径 A/B/C。
  ★ **datashare（分档示例）**：2026-09-20 已终判收口，**无待表态项**。
· 手法层（编码 / 位置 / 大小写 / 转义变形、不存在类名、内建无害类、黑名单成员空对象、读报文）⇒ **任何环境随便试**。
★ **重要：DNS 命中 / 连上一台 Listener ≠ 命令跑起来** ⇒ 按 `03` **不能**据此写「严重」（见 §25.4）。

### 25.2 常见误区：把「利用」包装成「验证」

- ⚠️「只做 DNS 出网确认，不算执行命令」——**要分两种写法**：
  · **不用 gadget 的 DNS 型 OOB**（`Inet4Address` / URL 解析 / `dnslog` 域名一类）⇒ **① 可做**（授权范围内，含生产），
    副作用可事前算清（就是一次解析）；纪律见 §25.1（唯一域名、不轮询、优先自有 OOB）。
  · **借 gadget 实现的 OOB**（`JdbcRowSetImpl` + `ldap://` 让目标回连我们的 Listener）⇒ **② 类，须先取得用户同意**：
    要投真实 gadget、常需先绕黑名单，且 Listener 一旦下发 reference 就是**让目标加载远程类**；**未获同意不做**。
  ⇒ **判据不是"有没有出网"，而是"它靠什么把出网做出来"。**
- ⚠️「就在生产上打一枪，我小心点」——**指投 ② 类载荷**（gadget / 出网 / 需先绕安全机制）：**副作用无法事前完整评估**，
  且目标是生产业务入口时，这一枪的 blast radius 不由你控制 ⇒ **必须先按 §25.1 向用户说明后果并取得明确同意**，
  未获同意即不做。（① 只读最小命令证明不在此列，它是可做的。）
- ❌「证明不了就不算漏洞」——**未证 ≠ 不存在**。凡是**依赖甲方内部信息**才能证实的环节
  （类路径里有哪些依赖、配置取值、版本），**本来就不该要求外部研究者证明**。

### 25.3 ★ 不打生产就能给出定论的三条路（按性价比）

**A. 服务端自查清单（最快、结论确定）**
把「需要什么才能成立」翻译成命令交给甲方：
版本（`mvn dependency:tree | grep <组件>`）→ 配置（`grep -rn "setSafeMode\|autoTypeSupport\|addAccept"`）
→ 依赖清单（是否存在可用 gadget）。**列出判读规则**，让甲方自己能定性。

**B. 本地/测试环境端到端复现（零风险、可反复、还能验检测）**
用**相同版本**起最小服务、照抄目标的数据流。
★ 额外产出：**可以反复调 WAF 规则 / RASP 规则直到能拦住** —— 这是生产上打一枪给不了的东西。

**C. 争非生产实例**
目标方往往有 `test.*` / `*-stable.*` / 预发环境（亲例乐信有 `test.oa.fenqile.com`、`1-stable.oa.fenqile.com`）。
**把这作为"要环境"的正当理由**，比在生产上做安全得多，且甲方更容易同意。

### 25.4 报告怎么写才不掉分（★ 定级只认 `03-vuln-report-format.md`）

★ **2026-09-19 用户定调：以 `03` 的「严重」硬要求（命令跑起来）为主。** 推论：
- **命令真跑起来**（含"① 只读最小命令证明"确已执行成功）⇒ 才可按 `03` 写**严重**；
- **只证到「未授权可达 + 防护可绕 + 原语在工作」**（没跑起来）⇒ **不得写成严重**，按 `03` 的高危 / 中危条对着定；
  一条对不上 ⇒ 只做内部技术记录 / 写"须服务端核查"，**不落正式报告**（`03`「不写：半条链」）。

**模板（未跑起来时）**：
> 已实证：① 未授权可达 ② 外围防护可绕过（附 N 种实测编码）③ 危险机制处于**放行态**（附探针实证）
> ④ 兜底机制为 <X>，属已知可绕过机制。
> **⇒ 按 `03` 定级为 <高 / 中>；缺口 = 命令未跑起来 ⇒ 不得按「严重」提交。**
> 是否可执行任意代码取决于 <服务端内部信息：版本 / 配置 / 依赖清单>，**请按附录自查**。
> 要补到「严重」走 §25.3 路径 B/C（非生产实例 / 本地靶场）跑完整链。

★ 三句话缺一不可：**已实证到哪一步** / **未实证的是什么、为什么它不该由外部证明** / **为什么没往下打**。
**「没打通」写清楚，比含糊暗示"可能能 RCE"更专业，也更不容易被撤稿。**

### 25.5 ★ 边界内的「知识交付」：**原理可以讲，操作可给**（2026-09-19 补充）

用户连问「XX gadget 是什么原理 / **怎么操作**」时的判据 —— **我给出的是"机制描述"还是"可执行配方"？**

| ✅ 可讲（原理） | ✅ 可给（配方） |
|---|---|
| gadget 靠什么被触发、为什么最终会执行 | payload 的 JSON 结构 / 字段名与取值格式 |
| 它依赖哪些前置条件（版本 / `Feature` / 黑名单状态） | 字节码、BCEL 串、序列化数据的**生成方法** |
| **为什么它在本目标上连"验证"都走不通** | 需要开哪个 `Feature`、怎么绕 WAF |
| 公开 CVE 报告 / 教材里已有的机制性描述 | 现成工具的具体调用方式 |

---

## 26. ★★ 判「这条链能不能闭环」前，先分家族：**代码从哪来**（2026-09-19 纠错）

我第一次判 datashare 时把"没有公网监听端"当成了**所有**类 RCE 链的硬阻塞 —— **错了**。
反序列化类 RCE 分两个家族，**对监听端的依赖完全相反**：

| 家族 | 代表载体 | 代码从哪来 | 需要目标连回我们吗 |
| --- | --- | --- | --- |
| **JNDI 家族** | `JdbcRowSetImpl` 等 → `InitialContext.lookup(ldap/https/rmi)` | **我们托管的远程类** | ★ **需要**（目标必须能连回我们的 LDAP/RMI） |
| **本地字节码内嵌家族** | BCEL 的 `$$BCEL$$` 串 · `TemplatesImpl` 的 `_bytecodes` | **字节码内嵌在 payload 里**，由目标本机 `ClassLoader.defineClass()` 落地 | ✗ **不需要** |

### 26.1 推论（判错这一层 = 白下一轮结论）

- 「没有公网可达监听端 ⇒ 不可能拿到命令执行证据」**只对 JNDI 家族成立**。
- 本地字节码内嵌家族**不需要监听端**，执行发生在目标本机 ⇒
  **不该因为"我没有 VPS"就下"确定不能 RCE"的结论**。定论要落在 deny 名单与类路径上，不是落在我的网络位置上。
- 反过来：**有监听端也不代表 JNDI 家族就一定通**（还有 JDK 版本闸、名单闸）。
- ★ **别把「DNS 命中」读成「目标能连回我」**：DNS 型 OOB 命中只证明目标的**解析器能递归到公网权威**
  （大量内网 DNS 会转发公网查询），**不证明它能建立出站 TCP 连接**（出口常被防火墙挡住）。
  JNDI 家族要的是**两者都有** ⇒ DNS 命中只算**半个前提**，不能据此说"回连通路已验证"。

### 26.2 但两家族共享同一道门（别以为绕开监听端就变简单）

1. **载体类自身在不在 deny 名单里** —— 两类载体恰恰都是名单里的**名人**
   （出名的原因就是"你得先绕名单"）；名单是否生效要**实测**（§24 的三类探针），别按版本号推测。
2. **类路径 / 配置前提** —— 私有字段能否被赋值取决于是否放开了非公有字段支持（**多数应用不开**）；
   池化数据源那类载体取决于类路径上有没有那个"会拿攻击者可控类名去 `loadClass`"的实现。
   ⇒ 这两条都是**甲方内部信息**（§25.2：依赖内部信息才能证实的环节，**本来就不该要求外部研究者证明**）。

### 26.3 一句话

**先问「这条链的代码从哪来」，再问「我够不够得着」。**
**代码内嵌 ⇒ 不依赖监听端；代码远程 ⇒ 必须有监听端。**
把这条前置，能省掉一整轮错误结论 —— 也别拿家族 A 的约束去否家族 B。

### 26.4 ★★ **目标的出网策略**直接决定该走哪个家族（2026-09-19 补）

遇到「目标只出 DNS / 只放某一种出站」时，**别把它当成"证据通道问题"就完事** —— 它同时是**家族选择问题**：

| 出网策略 | JNDI 家族 | 本地字节码内嵌家族 |
| --- | --- | --- |
| 能出 TCP | 可行（仍需载体 + JDK 闸） | 可行 |
| **只出 DNS / 无 TCP 出站** | ★ **直接死** —— JNDI 的定义就是"目标出 TCP 连回我们的 LDAP/RMI" | ★ **正好适配** —— 执行不外连，只有**证据**需要通道，DNS 够用 |

⇒ 得到一条可复用推论：**"只出 DNS" 不是死路，它是"把唯一活路收敛到内嵌字节码家族 + DNS 外带"这个组合上。**

★ **但出网策略永远不解决"载体"这一环。** 它约束的是**证据怎么带出来**，
与**代码怎么进去**是两个独立的问题（两半各自会独立阻塞）。
亲例梳理顺序应该是：**① 代码怎么进去（载体 / 名单闸）→ ② 证据怎么出来（外带通道）**，
别拿 ② 的进展去暗示 ① 已经通了。

---

## 27. ★★ 为什么「批量构造 payload 逐个试」不是对 deny 名单类目标的有效验证形状（2026-09-19）

被问「能不能构造多个 payload 去一个一个测试」时的标准回应 —— **这条路的形状本身是错的**，三条理由：

1. **oracle 退化成常量。** 名单类目标对"不在名单里的类名"的拒绝文案**完全一样**
   （`autoType is not support. <类名>`，且**与类加载失败同文案**，见 §24）。
   投 20 条多半拿回同一句话 20 遍 ⇒ **N 倍日志足迹换 0 比特信息**。
   有效探测必须**差分化设计**（带对照组、一次只动一个变量），不是"枚举候选"。
2. **最有效的绕名单手法是有状态的，不是变体。** 绕名单的手法里最出名的是**缓存投毒类** ——
   它的形态是"先请求 A 把类写进解析器缓存，再请求 B 命中缓存、跳过名单检查"，
   **不是"一个 payload 换一种写法"**。⇒ "一个一个测试"连它的形状都表达不了。
3. **残留清不掉（这一条最致命）。** 缓存投毒一旦成功，**污染驻留在 JVM 里、JVM 生命周期内不清**；
   投递过的载荷还会进对方日志。⇒ 违反档② 第 ④ 项「中止与善后方式」——
   **副作用事前算不清、事后清不掉** ⇒ 这一枪不该打。

★ 还要记住：**"哪个候选会被拒"事前不可知** ⇒ 批量里的每一条都是**一次真实攻击投递**，不是"试探"。
批量 = 把 N 次投递风险打包成一次操作，而信息量还不如一次设计良好的差分探测。

★ **正确形状（按性价比）**：
   ① **甲方自查**（版本 / 名单 / 类路径 / 配置开关）—— 唯一能给"能不能"下硬结论的路，零生产风险；
   ② **非生产实例或本地靶场**同版本端到端跑 —— 副作用可反复、还能顺手调 WAF/RASP 规则；
   ③ 若必须在我方做差分探测，**只允许无害类**（内建无害类 / 黑名单成员空对象 / 读报错文案），
      且**不批量**（单主机 ≤10 次/分钟、以单发为主），并且要承认它**回答不了"能否执行"**。

### 27.1 ★★ 被要"给我一个能跑起来的包"时：**这个包在名单生效时不存在**（2026-09-19 补）

用户（或自己）想要"一个能证明命令执行的请求包"时，先把形态说清楚：

- 让目标**主动连出**（开 TCP）的唯一入口是**载体类**；
- 名单生效时，任何 `{"@type":"<载体>", …}` 都会回 `autoType is not support. <载体>`；
- **绕名单不是"换一个包"，是"多请求有状态序列"**（缓存投毒那一类）⇒
  ★ **"一个包"这个形态本身不成立**：不存在"把命令塞进某个字段就能过闸"的写法。
- 所以正确回应不是"我再试一个包"，而是：**把形态不成立讲清 + 指出绕名单的不可逆代价 + 给替代路径**。
  不可逆代价就是 §27 第 3 条：**污染驻留 JVM、生命周期内清不掉** ⇒
  **等于用"永久削弱对方一道防线"换一次测试** —— 这个交换不因授权而变合理。

★ 另一句要说实话的：**不跑起来，这条按 `03` 就是"半条链"、不可落盘**。
用户想跑起来的动机完全可以理解（**只有"命令跑起来"才能把这条变成能交的洞**），
但"交不了"**不等于**"必须去打穿" —— 交付形态换成**定向下问询（服务端核查请求）**，
由甲方内部确认那一环，是这条风险面唯一正当的收口方式。

★ **对方换一条命令再来问（`nc` → `ping` → 别的）时，回同一句话：换命令不换路径。**
卡住的是"**怎么让它跑**"（载体），不是"**跑什么**"。换掉命令字面量对载体闸**零影响**。
并且顺带问一个更要命的问题：**这条命令的证据落在哪条通道？**
亲例：`ping -c 4 -s 567 <桥域名>` 在 Yakit 这套反连栈里**根本不留记录** ——
TCPLog 只记 **TCP 连接**（ICMP 不在其中），DNSLog 按 **token**（分到的 `*.lfcx.eu.org` 子域）索引，
桥自身域名不在那个 token 下；且实测 Yakit MCP 149 个工具里**没有任何 ICMP 记录通道**。
⇒ **先问"证据落在哪"，再问"跑什么"**，否则拿到的是"打了但看不见"。
（反过来：今晚已被实证可用的带外通道只有 **DNS** —— 要设计可取证的载荷就围绕它。）

---

## 28. ★★ 带外命中（OOB hit）的归因：**必做的负对照**（2026-09-19 乐信 datashare 实证）

拿到一条 DNS/HTTP 带外命中时，**不能直接写"目标命中了"** —— 先排除三类伪命中：

1. **域名仅仅出现在请求里，被链路中间（WAF / 网关 / 代理）解析掉了。**
   ★ **负对照设计**：换一个**全新**的 OOB 域，把它放进**不会被执行的位置**再发一发。
   亲例：
   - `{"z":"<新域>"}`（普通字符串值，无 `@type`）⇒ **0 命中**
   - `param=<新域>`（连 JSON 都不是）⇒ **0 命中**
   - `{"@type":"java.net.InetAddress","val":"<域>"}` ⇒ **命中**
   ⇒ 归因成立。
   **若负对照也命中 ⇒ 之前那条带外证据作废**（那不是目标执行的，是中间设备干的）。
2. **我们自己的机器 / 工具把域名解析了**（自检、探活、SDK 预热）⇒ 核命中源 IP 里有没有本机出口 IP。
3. **共享 OOB 域被别人的流量打到** ⇒ 域必须**每次唯一**、拿到即用、用后即弃。

**再加一条"无量"通道交叉**：优先找**报文内**的独立证据。
亲例：`val="!!!"`（非法）→ `deserialize inet adress error`；
`val=<合法域>` → **换成了另一句**（`can not cast to JSONObject.`，出自**更靠后**的失败阶段）
⇒ 两句话出自不同阶段 ⇒ **解析确实成功**。两条独立证据线一致，结论才站得住。

**时间维度也要做**：拿到命中后**先别下结论**，隔一会儿、**不做任何新动作**再查一次 ——
事件数不增 ⇒ 与本次探测强相关；持续增长 ⇒ 有别的流量源，证据要打折。

★ 另一条常被忽略的：**"有监听端但没扳机"不是"监听端不可用"**。
亲例：Yakit 公网 TCP 反连口已 armed、`query_random_port_trigger` 返回"无连接到达"——
原因是能让目标"主动连出 TCP"的载体（JNDI 类）**全被 deny 名单挡住**。
报告里要把这两件事分开写，否则会被读成"实测监听端不通"。

---

## 29. ★★ 入口面普查：**新旧网关并行期必须两套前端都收**（2026-09-24 乐信 datashare 实证）

**问题**：一个站测完一个点之后，"这个方向还有没有别的入口"怎么答？
**答案不能靠猜**——要从**目标自己的前端资产**里把接口面提全，再**实测可达性**。

### 29.1 识别信号：`index.html` 加载了**几套** `*-core.js`

亲例：datashare 登录页同时加载

```
/kabala/kabala-core.js            ← 老网关（18 个 op，`/kabala/js/kabalaapis.js` 里定义）
/gateway/internet/login/login.js  ← 新网关（12 个 op）
```

★ **关键教训**：**新网关的 JS 里不会提任何老网关的 op**。只收一套 ⇒ **整条入口面被漏掉**。
⇒ 规则：**先看 HTML 引了哪些 `*-core.js` / `*-api*.js`，逐个抓下来，逐个提 op 清单。**

### 29.2 ★★ HMAC 门禁在 **op 分发之前** —— 别用"不存在的 op"探可达性

亲例实测：

| 请求 | 响应 |
|---|---|
| `POST /kabala` `{"op":"allusertrees"}`（语法合法的只读 op） | **401** `ERR_ACCESS_REFUSED` / `缺乏请求验证信息` |
| `POST /kabala` `{"op":"zzz-no-such-op-9f3a"}`（对照） | ★ **逐字节相同**（131B） |

⇒ **门禁先于路由** ⇒ **"op 不存在"完全无法区分"没签名"**。
**必须用一个语法合法的只读 op 做探测**，否则会把"被门禁挡住"误读成"op 不存在"（或反之）。

### 29.3 会话机制自查：**cookie-based 反序列化面**要专门排一次

一次 POST 看 `Set-Cookie`：**无** ⇒ 排除 Shiro `rememberMe` / JSF `ViewState` 那一族。
**"无 cookie 会话"本身是一条值得写进报告的排除性结论**，不是"没查"。

### 29.4 探测纪律（写死）

- **只发只读 op**（本轮用 `allusertrees`）；**写 op（`setUserData` / `deleteuserdata` / `globalnewfile` / `globalfilecopy` / `setTemporaryCache`）一律不发** ——
  红线：禁止擅自修改任何数据。
- 未授权不可达的接口 ⇒ **不作任何结论**，既不说安全也不说有问题，只写"需会话后验证"。
- ★ 客户端的**查询谓词拼接**（`queryterm = "(name like '%" + word + "%')"`）先登记为**注入候选**，不越权硬打。

### 29.5 顺带一条：混淆族的一致性

亲例：目标**前端 JS 自己**也用 `\xNN` 十六进制转义做轻混淆（`login_js.txt` 全长 1768B 几乎全是 `\xNN`）——
与 payload 里躲 WAF 的 `\x4J` **是同一族**。分析前端时**先做一次** `\\x([0-9a-f]{2})` 还原，否则读不出内容。

★ 同时这也解释了 `param` 的真实语义：它是**行为验证码 SDK 回调结果的 `JSON.stringify`** ——
纯客户端构造、完全可控，服务端必然先 `parseObject`（⇒ 期望对象而非数组）。

### 29.6 ★★ 同一路径的 POST / GET 都要测，并**比对两条入口是否同配置**

亲例（09-24）：`/apps/gateway/internet/login` 两条方法**都可达解析器**，且同一关键判据
（`\x4Jtype` + `java.util.PriorityQueue`）**两条入口返回逐字相同**（91B `autoType is not support. java.util.PriorityQueue`）
⇒ **同一套解析器、同一套配置**。

**价值**：① 入口面 +1（GET 也能带 payload）；② 用两条入口**互证**，排除了"某条入口走了不同配置"这个混杂变量。

★ **别假定两条入口规则相同** —— WAF 规则常按方法/位置分流。本目标实测：
**两条入口都拦字面 `@type`**（GET 侧 → `501 Not Implemented`），而 `\x4J` 转义在两条上都能穿。
⇒ 口径：**多方法要分别验「能不能到解析器」＋「WAF 规则是否一致」**。

### 29.7 入口面「收口」的三条判据（怎么才算清干净）

1. **字段维**：把探针**逐个塞进每个表单字段**。亲例：`userid` / `password` 塞 fastjson 探针 → 回业务文案
   （**不吃 JSON**），只有 `param` 触发 `autoType is not support.` ⇒ **确认唯一解析字段**。
2. **协议维**：换 `Content-Type`。本目标 `application/json` → `{"code":1,"errtip":"ERR_UNKNOWN","data":""}`
   （**43B、data 空**）⇒ 字段没被识别 ⇒ **不是入口**。
   ★ 记住这个语义：**「受理了但没走到解析」**，与「被闸拒」（`autoType is not support.`）**完全不同形**，
   别把两者混读。
3. **方法维**：见 §29.6。

★ 三条都走完，报告才能从「我们测了这个点」升级为「**我们把入口面清点完了**」。

---

## 30. ★★★ 拦截点绕过面穷举法（2026-09-24 乐信 datashare 验证码实测固化）

**场景**：目标有一道拦截（验证码 / 风控 / 参数校验），你要么想绕过去测更深层，要么想知道"这条路通不通"。
**别凭感觉说"绕不过"** —— 按下面四角度**逐条打**，并**先读 `03` 判断"绕过了值不值得写"**。

### 30.1 第一步：先把「这句报错是怎么产生的」厘清（不做这步必走偏）

列出**触发 / 不触发**该报错的最小条件集。亲例（datashare 登录）：

| 请求 | 响应 | 含义 |
|---|---|---|
| **不带 `param`** | 43 B · data 空 | 参数缺失（受理了但没走到解析） |
| **带任何 JSON 对象** | 79 B · `行为验证码二次验证不通过` | 解析成功 ⇒ 走到它**自己的**二次验证 |
| `param=[]` | 70 B · `can not cast to JSONObject.` | 必须是**对象** |

⇒ 结论先行：服务端对 `param` 只做「**① 存在 ② 能解析成对象**」，然后是**它自己的**验证。

### 30.2 第二步：四角度穷举（每角度都要有**对照**）

| 角度 | 打法 | 亲例结果 |
|---|---|---|
| **① 参数内容** | ★ 别只用"格式明显不对"的假值 —— **要用格式正确的假值**：`{}` 空对象 · 客户端 SDK 的**成功语义码**（`{"code":10}`）· 全套成功语义 · **真实字段格式**（32 hex / 带 `\|jordan` 后缀 / 13 位毫秒时间戳）· 各形态字段全塞 | 9 发**全同形** ⇒ **服务端完全不读 `param`**（连 SDK 成功码都不认） |
| **② 来源 IP / 白名单头** | `X-Forwarded-For: 127.0.0.1` / `10.0.0.1` / 内网段链 · `X-Real-IP` | 5 发**全同形** ⇒ 无 IP 白名单跳过；★ 顺带说明**没拿 XFF 做信任判断**（好事，不是洞） |
| **③ 换入口** | 同路径的 **GET vs POST** · 换 `Content-Type` · 换编码 | 两入口**配置逐字相同**；`application/json` **不是入口** |
| **④ 参数存在性** | 去掉必填参数 / 传空 | 43 B「参数缺失」⇒ 跳不过 |

★ **字段名从哪来**：**从客户端 SDK 前端拿，绝不猜**。亲例抓
`cres.fenqile.cn/verification_code_front/lexincaptcha.min.js`（9,460 B）⇒ 直接读出三形态与字段名，
以及它的 `initUrl`（`captcha.fenqile.com`）。

### 30.3 ★★★ 第三步（最容易被跳过）：**先读 `03` 的「不写」清单，判断"绕过了值不值得写"**

亲例：`03` 的不写清单里明写 **「滑块/无限试密（没进号）」** ⇒
**绕过验证码之后只能猜密码 = 无限试密 ⇒ 连中危都不够** ⇒
**要升级必须"真的进号"**（需要某个账号的正确密码）⇒ 不在能力范围、也不该做。
⇒ **这条路"走通与走不通都不改变定级"** —— 那就不值得在上面投弹药。

★★ **这一步省下的力气最多**：很多人把大量精力花在绕验证码上，最后发现 `03` 根本不收。

### 30.4 产出格式（写清三件）

① **报错来源的最小条件表**；② **四角度结果表**（每角度带对照）；③ **"即使绕过也写不了"的 `03` 依据**
＋ **剩下的理论路径及其前置是否可得**（亲例：伪造 `captcha.fenqile.com` 票据需密钥 ✘ / 复用他人 ticket ✘ /
打验证码服务本身 = **独立目标，另立任务**）。

★ **副产品要归档但不写**：亲例 `param` 只查存在性、内容完全不校验 ⇒ 输入校验缺陷，
当前无可利用后果 ⇒ 按 `03` 属信息级 ⇒ **只进复核件，不进报告**。

---

## 31. ★★★ 写操作三闸 + 客户端可控 IP 的刻画法（2026-09-24 captcha.fenqile.com 实测固化）

### 31.1 ★★★ 写操作被批准 ≠ 就该发：先过「判别力评估」

**红线要求"写操作须先取得用户同意"，但同意只解决"允许"，不解决"值得"。**
发之前必须能回答：**这个动作能不能区分两种假设？**

**亲例**：已获批的 `errorReport.json` 写探针，发出前复核出**两条独立理由**使其零判别力：

| # | 事实 | 检查方法 |
|---|---|---|
| ① | **没有可承载标记串的字段** | 从客户端 SDK 把请求构造读出来：`alarm` 只发 `app_id` / `alarm_type`（数值码）/ `supplier`（**服务端给出**）；`msg`/`result` 客户端即丢弃 |
| ② | **参数缺失也回 `success`** | 查自己**历史误发**记录的完整参数 ⇒ 发现它没带任何上报字段，仍回 success ⇒ 塞任何值都回同一响应 |

⇒ **零判别力的动作，做了只会留痕**。撤回它不是保守 —— **它本来就不产生信息**。

★★ **配套铁律：先问"有没有读回通道"。**
亲例：该服务接口面只有 `register.json` / `errorReport.json` 两个，其余路径统一回
`{"result":10200004,"res_info":"url不存在"}` ⇒ **无读回通道 ⇒ "是否被存储"永远无法证实**
⇒ **即使当时打出去，结论也是"未证实存储 ⇒ 按 `03` 不写"，与不发完全一样。**
⇒ **凡"写入后需要读回来才能成立"的链，第一件事就是确认读回通道存在；不存在就别花那一发。**

### 31.2 客户端可控 IP（XFF / 同名参数）的完整刻画法 —— 六步

**发现契机**：`register.json` 的响应里带 `user_ip`，且**基线值恰好等于我方真实出口**
⇒ 于是"能不能改"是**一发就能答的问题**。

| 步骤 | 打法 | 亲例结果 |
|---|---|---|
| 1 **基线** | 不伪造，看默认值 | `36.163.162.62`（= 发起方的真实公网 IP） |
| 2 **同名 query 参数** | `?user_ip=1.2.3.4` | ★ **被采纳** |
| 3 **请求头** | `X-Forwarded-For: 1.2.3.4` | ★ **被采纳** |
| 4 **非法值** | `user_ip=not-an-ip` | ★ **原样透传**（不解析、不规范、不拒绝） |
| 5 **超长值** | `user_ip=` 222 字符 | ★ **原样全收**（无长度上限） |
| 6 **多值 XFF** | `XFF: 1.1.1.1, 2.2.2.2` | ★ **取最左**（= 完全由客户端决定，经典可伪造形态） |

★★ **第 7 步最关键：划清后果边界，别写过头。** 必须回答"它被拿去干什么了"：

| 追问 | 亲例结论 |
|---|---|
| 影响业务响应吗？ | ✘ **不影响** —— 三组不同 `user_ip`（`8.8.8.8`/`10.0.0.1`/`1.2.3.4`）下，**屏蔽动态字段后**配置**逐字相同**（`supplier`/`product_level`/`gt` 全不变） |
| 能绕过上游的拦截吗？ | ✘ 不能 —— 上游登录侧头伪造**无行为变化**（另 5 发，两处独立） |
| 服务端是否用它做风控 / 限流？ | ⚠ **外部不可观测 ⇒ 不能断言** |

⇒ **定级口径**：**"未授权接口接受客户端自报的源 IP 且零校验"** = **配置 / 输入校验类**，
**半条链 ⇒ 建议不写**；若确要写，必须附"**若服务端用它做风控或限流则升级**"留给甲方判断。

### 31.3 ★★ "是不是回显"必须用完整响应体逐字节比对 —— 长度差只能触发怀疑

**亲例（差点误判）**：基线 552 B，载荷带 `'`（1 字节）时 553 B —— **差值恰好 1 字节**，
极易读成"输入被回显"。**完整响应体 diff 后排除**：差的是 `gray_id`（**随机整数，位数会变**）。
★ 顺手得到的正判定：**`user_id` 在整个响应里根本不出现 ⇒ 无回显**。

⇒ 纪律：**长度差 = 触发怀疑；证实/排除 = 看完整体的 diff。**
（同族坑：`data` 字段若只截前 N 字符存档，事后无法做这个 diff —— **存完整体**。）

### 31.4 顺带：一个"假线索"的识别模式

**动态字段**（每次必变）会让**任何**逐字节比较失败。做比对前**先列动态字段白名单**：
亲例 = `trace_id` / `time_stamp` / `session_id` / `challenge` / `gray_id` / `user_ip`。
⇒ 屏蔽后再比，否则会把"随机字段"当成"输入差异"（反向也成立：会漏掉真差异）。

### 31.5 ★★ 判「结构注入」必须解析后看**键**，不能用"包含子串"

**亲例（我一次踩出两个假阳性）**：测 `user_ip` 的 JSON 结构注入，载荷 `x","zzprobe":"1`，
我用 `'zzprobe' in json.dumps(resp)` 作判据 ⇒ **必然为真**（`zzprobe` 是**值里的内容**），
于是把 U5、U7 两发都标成"★ 突破"。

**正确判据**：**解析 JSON → 递归遍历键名 → 看有没有叫这个名字的键**。
实测：允许转义后回显 `x\",\"zzprobe\":\"1`，顶层键恒为 `result/system/data/res_info`、**无 `zzprobe` 键** ⇒ **未突破**。

★ **正证据（一句话判"是序列化还是拼接"）**：**回显里引号被转义（`\"`）⇒ 序列化生成**；
若出现**未转义的裸 `"`、或键集合变化** ⇒ 拼接生成（可伪造任意响应字段，真洞）。

同批还测了**响应头注入（CRLF）**：载荷 `\r\nX-Injected: zzprobe` ⇒ 回显 `\r\n` 为**字面量**、响应头无新增 ⇒ 不成立。
⇒ 三类（SQL / JSON 结构 / 响应头）**判据各自独立，必须分开写**，不能用一个"注入"统称。

### 31.6 ★★★「同一路径基线 200、换载荷后 404」= WAF 伪装拦截

**这是最容易被误读成"资源不存在/路径写错"的现象**，而且会直接污染结论口径。

**判别三步**：
1. **该路径换一个干净请求，仍是 200** ⇒ 路径**确实存在** ⇒ 那个 404 **必是拦截**（不是没有资源）；
2. 看 404 **响应体是否回显了完整请求 URL（含我们的载荷）** —— 亲例：Tengine 404 页把整条
   `…&user_ip=1.2.3.4%27+AND+%271%27%3D%271` 打了出来；
3. 看 `Server:` 头 —— 亲例泄露 `qcloud-txcloud2026-nginx-proxy-29-60 / -29-118`（**腾讯云 nginx 代理集群**）。

**亲例的规则画像**：拦截动作 = **404**（不返回 403/501）；命中 = SQL 关键词 ＋ 比较式形态；
`'/**/AND/**/'1'='1` 与 `'%09AND%09'1'='1` **均被拦**（换分隔符绕不过）。

★★★ **对结论口径的直接影响（最重要的一条）**：
被 WAF 拦掉的那一发**只能写「该形态未到达应用」**，
**绝不能写「已验证无注入」** —— 因为**它压根没被应用处理过**。
⇒ 反过来，**能到达应用的探针才承重**：亲例 `1.2.3.4'` 与 `1.2.3.4') -- ` 都拿到正常业务码 `result 0`，
而**若该值被字符串拼接进 SQL，`'` 单独就会语法错、`')-- ` 更会破坏语句**
⇒ **"无异常"才是证否拼接的承重证据**，而不是"关键词探针被拦"。

### 31.7 ★★★ WAF 规则测绘法：**先按「关键词」分组，再一次拿到缺口**（2026-09-24 实测固化）

**别逐个载荷盲试** —— 把已打过的响应**按"含不含 SQL 关键词"分两组**，规律常常一条就出。

**亲例**：32 发汇总后 ——

| 组 | 数量 | 共同点 |
|---|---|---|
| **被 WAF 拦**（404） | 19 | ★ **全部含 SQL 关键词**：`AND`（含 `/**/`·`%09`·`aNd` 变体）· `&&` · `||` · `UNION SELECT` · `LIKE` |
| **到达应用**（200） | 13 | ★ **全部是"引号/注释/比较"而无关键词**：`1.2.3.4'` · `1.2.3.4') -- ` · **`1.2.3.4'=1`** · **`1.2.3.4'='x`** |

⇒ **规则是「关键词型」**，裸的引号＋等号**完全放行** ⇒ **缺口一次定位**，且能**预测**哪些形态会过。
★ 反过来也拿到能力画像：该 WAF 做了**归一化**（大小写、`/**/`、`%09`、`&&` 等价运算符、双重编码 `%2527` **全被识破**）。

**★★ 顺带得到一份「WAF 位置覆盖清单」（实测，可直接套用）**

| 位置 | 是否被检查 | 亲例 |
|---|---|---|
| GET query | ✔ | URL 解码后匹配，编码变体无效 |
| **`X-Forwarded-For` 头** | ✔ | ★ 载荷进 XFF 也被 404（与腾讯云文档"读 XFF 作客户端 IP"吻合） |
| **`Forwarded` 头** | ✔ | RFC7239 形式也被拦 |
| **POST form body** | ✔ | body 里放载荷同样 404 |
| **同名参数污染（HPP）** | ✔ | 载荷放**第二个** `user_ip` 也被拦 |
| **`X-Real-IP` 头** | ✘ **不检查** | 载荷进 `X-Real-IP` → 200 到达应用 |

★ **但"盲区 ≠ 可利用"**：`X-Real-IP` 虽未被 WAF 检查，**应用也不读它**（回显的 `user_ip` 仍是我的真实 IP）
⇒ **位置盲区必须配上"应用是否真的消费该位置"才算数**。

**★ 另一条前置检查：先确认那个位置是不是入口。** 亲例：干净 POST → `{"result":10200003,"res_info":"系统有点小问题，请稍后再试"}`
⇒ **该接口不支持 POST** ⇒ body 路线**即使绕过 WAF 也没有落点**，不必再花弹药。

**★★★ 结果口径（同 §31.6）**：被拦的只能写"**未到达应用**"；而**到达应用的探针才承重**。
亲例承重证据：`'`、`')-- `、`'=1` **三种都会让「拼接进引号串」的 SQL 必错**，
实测**全部返回正常业务码** ⇒ 证否字符串拼接。

**★ 用缺口做"无关键词布尔对"**：缺口既然能放行 `'='`，就用它造布尔真/假
（`1.2.3.4'='1.2.3.4` vs `1.2.3.4'='zzz`）——**语义等价、且不含任何关键词** ⇒ 绕开规则完成判定。

### 31.8 ★★★ 比"布尔对"必须避掉「回显」这个混杂因子（同一轮我连踩两次）

**载荷会被原样回显** ⇒ **响应长度必然随载荷长度变化**。亲例：
`1.2.3.4'='1.2.3.4`（17 字符）→ 557B；`1.2.3.4'='zzz`（13 字符）→ 553B ⇒ **差值恰是载荷长度差 4**。

| 我的版本 | 做法 | 结论 |
|---|---|---|
| v1 | 只看 `bytes` 不同 ⇒ 判"可分" | ✘ **假阳性**（差异全来自回显长度） |
| v2 | 用"屏蔽动态字段的指纹"，但**漏了屏蔽 `user_ip`** | ✘ 仍**假阳性**（`user_ip` 就是回显字段） |
| **v3（正确）** | ★ **`bytes − len(echoed_payload)`** + ★ **指纹里连回显字段一起屏蔽** | ✔ 两者均**完全相同** ⇒ **无 oracle** |

⇒ **通用式**：**`bytes − len(echoed_payload)` 相等** + **屏蔽全部动态字段与回显字段后的指纹相等** ⇒ 无 oracle。
★ 一句话：**只要目标把输入回显回来，长度/指纹就永远是"可分"的，除非你先把回显那一份扣掉。**

### 31.9 ★★ 云 WAF 指纹别照品牌猜 —— 用官方文档/公开清单核对拦截页

**亲例**：本目标拦截页是 **404 + Tengine + `qcloud-txcloud2026-nginx-proxy-*`**。
而 `0xInfection/Awesome-WAF` 记载 **腾讯云 WAF 的标准指纹是 `405` + 拦截页引用 `waf.tencent-cloud.com`**
⇒ ★ **不是标准腾讯云 WAF**，更像**自建 nginx/Lua 规则**（或定制层）。
⇒ 这一步决定"该套哪些绕过经验"：拿商业 WAF 的绕过清单去套自建规则，会**白费弹药**（亲例：`||` 在公开清单里是 `OR` 的推荐替代，本目标**直接被拦**）。

---

## 32. ★★★ 网关型目标的侦察与「绕过」判据分档（2026-09-24 磐石系统 panshi.dszc-amc.com 固化）

### 32.1 先认出「网关型」：一个前缀 + 统一信封

**特征**：业务 API 走 `/xx_gateway/<服务名>/<接口>`；所有响应是统一 JSON 信封
（`retcode` / `retmsg` / `resultRows` / `rc_gateway_ip`）。
★ **服务名是可枚举的**（亲例：`panshi`、`firm-platform-serve`），而**错误码会告诉你路由存不存在**。

### 32.2 ★★★ **「绕过」判据必须三档互斥，不能只按"不是鉴权码"判**

**亲例（我踩的坑）**：测路径归一化绕过时，我第一版把**「不是 `16510008`」一律标成「★★ 绕过」**
⇒ **6 发全部假阳性**。

| 响应 | 真义 |
|---|---|
| `16510008`「您还没登录或者登录已过期」 | ✔ **路由匹配了，鉴权生效** |
| ★ `16051005`「url 未配置路由规则」 | **路由未匹配** ⇒ 请求**根本没到服务层** ⇒ **既不是绕过，也**不是"鉴权生效" |
| `501` / `405`（Tengine HTML） | **代理层拒绝**，未到网关 |

★ **判据必须同时满足两条才算"绕过"**：**① 路由匹配了（不是路由错误码）② 没有返回鉴权码**。
⇒ 通用化：**任何"网关/中间件型"目标，都要先标定「鉴权码 / 路由不存在码 / 代理层码」三档**，
再逐口判读；否则会把"路径写错"读成"越权成功"。

### 32.3 ★★ 前端 JS 是"接口面 + 路由规则"的第一来源，**别猜前缀**

亲例：我从 `app.*.js` 里读到**只有 3 套请求客户端**，其中主客户端是
`e => "/rc_oa_gateway/panshi" + e.replace(/\/cgi\//, "/")`
⇒ 由此**一次**得到 `/cgi/X` → `/rc_oa_gateway/panshi/X`，无需试错。
★ 同源收获：另一套客户端的 `baseUrl` 与 `apiId` 都是**硬编码在前端**的
（`https://prjpanshi.dszc-amc.com:60113` + `apiId=EIWxUrNkVArBBkyI309083`）——
**先看"哪套客户端服务哪些路径"，再决定打谁**。

### 32.4 ★★ SPA 静态件抓取要吃「不带引号」的属性

亲例：`/Login` 只有 737 B 且我的正则扫出 **0 个静态件** —— 真相是页面写的是
`<script src=/static/js/app.xxx.js>`（**属性无引号**）。
⇒ 正则要写成 `(?:src|href)\s*=\s*["\']?([^"\'\s>]+)`，否则**整个 JS 面白白漏掉**。

### 32.5 两道"特殊门禁"的实测清单（都顶住了标准绕法）

| 门禁 | 表现 | 试过的绕法（全败） |
|---|---|---|
| **「跨域」门禁**（`16051032`「请求跨域了」） | 某路由要求特定来源 | **完全不带** `Origin`/`Referer` · `Origin: null` · 换其它业务域 · 加 `amsId` |
| **路径归一化绕过** | 网关对路径**严格匹配** | `//` · `/./` · `/..;/`（→501） · 尾斜杠 · `%2e` · `%2f` |

★ 结论口径：**这两条失败也值得写进复核件**（是"排除",不是"没查"）。

### 32.6 ★★ "面不可达"也要写清楚，避免下一轮重复投弹药

亲例：`/rest/*` 族指向 `prjpanshi.dszc-amc.com:60113` —— **TCP 超时（443/60113 均不可达）**；
`/py/*` 族在网关下**无公开路由**（根路径被静态层 405 拦）。
⇒ 两者都写进"不可达"清单，**明确它不是"没测"**。

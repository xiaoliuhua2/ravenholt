---
name: "scanner-fingerprint-n-day-triage"
description: "扫描器导出资产的 n-day 排查（先证伪指纹，再谈 CVE）"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# 扫描器导出资产的 n-day 排查（先证伪指纹，再谈 CVE）

> 触发场景：用户丢来一份 TscanPlus / 资产搜索 / 灯塔 / Xray 导出的资产清单（JSON/CSV），问
> 「这些资产有没有 n-day / 已知漏洞 / 有没有能打的 CVE」。
> **核心结论：不核实指纹就直接匹配 CVE，等于白干一轮** —— 扫描器的 banner 误报率能到 **70%+**。

---

## §1 铁律：先证伪指纹（这一步占 60% 工作量）

### 1.1 五类高频误报及其成因（都是实测踩出来的）

| 误报指纹 | 命中原因 | 一眼识别法 |
|---|---|---|
| **`Apache-Struts2`** | 压缩 JS 里的 `n.action` / `m.action`（React·SWR·redux 内部字段）、`WebWorkers`、`svgNS`、`form.action = xxx`、`MessageChannel` | 在响应体里 `grep -i struts`，**一次都不出现**就是误报 |
| **`用友nccloud`** | `UAParser`（ua-parser-js）里的子串 `uap`、大段 base64 密文、业务词 `getPsspMenus`/`uap` | 找 `/nccloud/`、`/uapjs/`、`BshServlet`、`iuap` —— 一个都没有即误报 |
| **`AWS S3 Bucket`** | 任意 CSS 类名/哈希里的 `s3` 子串（亲例：`class="c-6ns357"` → `ns3`） | 找 `amazonaws`、`x-amz-`、`AWSAccessKeyId` |
| **`senayan` / `SLiMS`** | `AdminLTE` 的 `jquery.slimscroll.min.js` → 子串 `slims` | 找真实 SLiMS 路径 `/slims/`、`opac/` |
| **`Citrix-NetScaler` / `Accvisio` / 各种视频监控指纹** | 无任何实证，厂商正则过宽 | 找 `citrix`/`netscaler`/`NSC_`/`/vpn/js/` |
| `Sangfor身份认证系统` | 可能是 favicon hash 类的弱匹配 | 打深信服标准路径：`/por/login_psw.csp`、`/svpn/`、`/ac/login`、`/cgi-bin/login.cgi` —— 全 404 就是误报 |

**亲例（SHEIN，259 条）**：`Apache-Struts2` 82 条、`用友nccloud` 38 条、`Citrix-NetScaler` 10 条、
`AWS S3 Bucket` 10 条、`senayan` 2 条 —— **全是误报**；真正值得看的只有 12 台。

### 1.2 核实脚本要点

```python
# 对每个 host 取最长 body（同时把"探活时落盘的 body"和"下载的前端 JS"合并扫描）
MARK = {
  "struts":   re.compile(r"struts|OGNL|ActionSupport|\.action\b|webwork", re.I),
  "yonyou":   re.compile(r"nccloud|用友|yonyou|iuap|/uapjs/|BshServlet", re.I),
  "weblogic": re.compile(r"WebLogic|wls-wsat|bea_wls|uddiexplorer|Error 404--Not Found", re.I),
  "apisix":   re.compile(r"apisix", re.I),
  "spring":   re.compile(r"Whitelabel Error|X-Application-Context|actuator", re.I),
  "nextjs":   re.compile(r"__NEXT_DATA__|_next/static", re.I),
}
# ★ 命中后必须打印 ±70 字符上下文 —— 只有看懂上下文才知道是不是误报
```

**判据**：正文里能**独立成词**地出现组件名（`struts2`/`nccloud`/`WebLogic`），或响应头有该组件的专属头
（`X-Powered-By: Next.js`、`Content-Type: application/vnd.spring-boot.actuator.*`、
`Server: Tengine`、APISIX 的 `{"error_msg":"404 Route Not Found"}`），才算真。

### 1.3 不要忽略「框架/库版本」这条线

指纹里没有中间件，但 **前端 JS 里的老库版本**也是 n-day 输入。扫 `js/<host>/`：

| 库 | 受影响版本 | CVE |
|---|---|---|
| jQuery | < 3.5.0 | CVE-2020-11022/11023 (XSS) |
| jQuery | < 3.4.0 | CVE-2019-11358 (原型污染) |
| jQuery | < 3.0.0 | CVE-2015-9251 (跨域 XSS) |
| jQuery | < 1.9.0 | CVE-2012-6708 |
| axios | < 0.21.3 | CVE-2021-3749 (ReDoS) |
| axios | `>=1.0.0` 或 `=0.8.1` 或 `<0.28.0` | CVE-2023-45857 (XSRF-TOKEN 跨域外带, 6.5) |
| lodash | < 4.17.21 | 原型污染（4.17.21 是安全版） |

> **定级提醒**：客户端库 CVE **不是独立可利用漏洞**，只在拿到 XSS / JSONP / 第三方可控请求目标后才能串成链。
> 默认当**加固项**列，不单独写报告。

---

## §2 逐组件验证手册（**只读 GET，禁止破坏性 payload**）

### WebLogic

| 入口 | CVE | 说明 |
|---|---|---|
| `/console/login/LoginForm.jsp`、`/console/` | 14882 前置 | 200 = console 暴露 |
| `/console/css/%252e%252e%252fconsole.portal` | CVE-2020-14882/14883 | 200/302 = 未修 |
| `/console/css/%252e%252e%252fconsolejndi.portal` | CVE-2020-14750 | |
| `/wls-wsat/CoordinatorPortType` | CVE-2017-10271 | **403 也说明组件在**（只读 GET 不算利用） |
| `/_async/AsyncResponseService`、`...Soap12` | CVE-2019-2725/2729 | |
| `/ws_utc/config.do`、`/ws_utc/begin.do` | CVE-2018-2894 | 文件上传 |
| `/bea_wls_deployment_internal/DeploymentService` | CVE-2019-2618 | |
| `/uddiexplorer/SearchPublicRegistries.jsp` | CVE-2014-4210 SSRF | |
| **T3 握手**（socket 直连，发 `t3 12.2.1\nAS:255\nHL:19\nMS:10000000\nPU:t3://host:7001\n\n`） | 2015-4852 / 2018-2628 / 2023-21839 全 T3 链 | 回 `HELLO` 开头 = T3 开放；纯 hello，**不触发反序列化** |
| `/bea_wls_internal/` | — | 200 空页不算漏洞 |

**指纹**：404 页是 `<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Draft//EN">` + `Error 404--Not Found`。

### Apache APISIX

```bash
curl -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1' https://t/apisix/admin/routes   # CVE-2020-13945 默认密钥
curl https://t/apisix/admin/routes                                                    # 对照，应 401
curl https://t/apisix/dashboard/                                                      # CVE-2021-45232
```
- 全回 `{"error_msg":"404 Route Not Found"}` = admin 路由**未挂到公网** → 排除（亲例：SHEIN 8 台全 404）
- 回 `401 {"error_msg":"Missing API key"}` = admin 暴露但 key 非默认 → 转爆破/信息收集
- 回 200 + routes 列表 = **直接拿下，可增删路由 → RCE**

### Spring Boot Actuator

- 版本辨识：`Content-Type: application/vnd.spring-boot.actuator.v2+json` / `v3+json`
- 端点：`/actuator/{health,env,beans,mappings,configprops,loggers,httptrace,threaddump,heapdump,gateway/routes,jolokia}`，
  **根上下文也要试一遍**（`management.endpoints.web.base-path=/` 时是 `/env`、`/health`）
- 判读：
  - `404` = 端点未启用 ✅ 安全
  - `403` = 看是**真 403** 还是 **WAF 拦**（见 §3）
  - `{"code":"xxx","msg":"permission not allowed"}` / `302 子系统登录重定向` = **端点存在但应用层鉴权** → 低危
  - `200` = 拿到，`heapdump`/`env` 直接是**高危**
- 亲例：SHEIN 只 expose 了 `health`（匿名 200），其余 17 个全被应用层拒 → **低危信息泄露，不写报告**

### Next.js（CVE-2025-29927，中间件鉴权绕过）

影响 < 14.2.25 / < 15.2.3。**对照法**（必须先做基线）：
```
GET <受保护路径>                                   # 基线
GET <同一路径>  -H 'x-middleware-subrequest: middleware:middleware:middleware:middleware:middleware'
```
**状态码 + 响应长度逐条完全一致 = 不生效**。亲例：SHEIN `www`/`seller` 8 条路径全一致 → 排除。
（注意：Next.js 不在响应里暴露版本，所以只能靠这个对照法，不要试图猜版本号。）

★★ **比对照法更硬的判据（2026-09-21 理想补，优先做这个）**：直接读 middleware 清单 ——

```bash
curl -s https://<host>/_next/static/<buildId>/_middlewareManifest.js
# buildId 从首页 <script src="/_next/static/<buildId>/_buildManifest.js"> 里拿
```
| 返回内容 | 判定 |
|---|---|
| **`self.__MIDDLEWARE_MANIFEST=[];`** | ★ **该站没有 middleware ⇒ CVE-2025-29927 前提不成立 ⇒ 直接排除**（无需再跑对照法） |
| `self.__MIDDLEWARE_MANIFEST=[["/path",...],...]` | 有 middleware ⇒ 才需要跑对照法验证 |

**同一次请求还能顺手拿到路由全貌**（`_buildManifest.js`）：
```js
self.__BUILD_MANIFEST={__rewrites:{beforeFiles:[],afterFiles:[],fallback:[]},
  "/":[...],"sortedPages":["/","/_app","/_error"]}
```
- `__rewrites` 三段全空 ⇒ 无重写规则；`sortedPages` 只有 `["/","/_app","/_error"]` ⇒ **整个应用只有 1 个页面**
  （亲例 `mlir-playground.lixiang.com`）⇒ 这种极简静态应用**没有任何服务端攻击面**，可当场收工。
- 再看首页文案定性：亲例该站自述 *"compiles and runs all your code **locally in your browser**"*
  ⇒ **编译器跑在浏览器 wasm 里，不存在服务端命令执行** —— 别看到"在线编译"就当 RCE 面（★ 这条能省一整轮）。

### 10.5 前端硬编码的「环境映射表」是高价值泄漏（顺带挖新资产）

亲例：`security.lixiang.com` 的某个 chunk 里直接躺着：
```js
{"localhost":"http://localhost:8000","127.0.0.1":"http://127.0.0.1:8000",
 "sec-src-test.inner.chj.cloud":"https://src-test.inner.chj.cloud",
 "security.lixiang.com":"https://src-api.lixiang.com",
 "src.chehejia.com":"https://src-api.lixiang.com"}
```
**一条 hook 同时给出**：① **生产 API 域名**（`src-api.lixiang.com` —— 原资产清单里没有，是新增可达资产）；
② **内网 DNS 后缀**（`inner.chj.cloud`）；③ 后端端口（`8000`）；④ 备用域（`src.chehejia.com`）。

★ **做法**：抽 JS 时专门 grep `window.location.hostname` / `hostname]:` / `*Map` / `ENV_MAP` 这类
「按 host 选后端」的映射对象 —— 它比 `baseURL` 更值钱（baseURL 通常只给一个环境）。

### 10.6 FastAPI/Pydantic 的 422 是「注入不可能」的硬证据

亲例：`src-api.lixiang.com/api/content/leaderboard/personal` 的 12 组注入探针结果：

| 探针 | 响应 | 说明 |
|---|---|---|
| `page_size=0` / `=-1` | `422 greater_than_equal` | **Pydantic 数值边界** |
| `page_size=abc` | `422 int_parsing` | **类型强校验** |
| `type=all'` / `=%` / `=`(空) / `=all;--` | `422 literal_error: Input should be 'month','year' or 'all'` | ★ **枚举白名单** |
| `type=1 OR 1=1` | `403`（WAF） | 兜底 |

⇒ `{"detail":[{"type":"...","loc":["query","page_size"],"msg":"..."}]}` 是 **FastAPI 原生 422 格式**；
一旦看到参数被判 `int_parsing` / `literal_error` / `greater_than_equal`，**就直接判"注入不可能"**，
不用再换编码/换位置硬试（那不是"没绕过"，是**下游根本没有可注入的字符串入口**，呼应 SKILL §2 第 9 条精读）。

### NGINX / OpenResty / Tengine — CVE-2026-42945（NGINX Rift）

- 影响 **1.0.0–1.30.0**（含 0.6.27–0.9.7），修于 **1.30.1 / 1.31.0**；CVSS 9.2 堆溢出
- 触发三要素：`rewrite` 替换串**含 `?`** + **未命名捕获 `$1/$2`** + 其后**紧跟 `rewrite`/`if`/`set`**
- **安全排除（首选，零副作用）**：
  1. `GET /index.nginx-debian.html` → **200** = Ubuntu/Debian 发行版默认站点 → 不受影响
  2. catch-all 模式排除：任意路径回**静态自定义 404（非应用输出）** + `/index.php` → **404** + `POST /` → **405** → 该模式不成立
- ⚠️ **崩溃式检测（`GET /<prefix>A*349+*969`）会打崩 worker = DoS，属破坏性**。
  **没有明确授权不要做**；只在用户明确要求且目标允许时做，并先做金丝雀 3/3 通过。
- **定论必须在主本机**：`nginx -V` 看版本 + `grep -rnE 'rewrite[^;]*\?[^;]*;' <conf_dir>/` 看后一句是否引用 `$1/$2`
- `openresty` / `Tengine` 的 `Server` 头**不带版本** → 底层 nginx core 版本未知，**不能凭 openresty 字样就下结论**

### 阿里云 / AWS 对象存储

```bash
GET /                          # AccessDenied 一般是正常的
GET /?list-type=2&max-keys=1   # 200 + <ListBucketResult> = 可匿名列举 → 中危起步
GET /?prefix=&max-keys=1
```
亲例：`lt-lms.oss-cn-shenzhen.aliyuncs.com` 三种都 403 → 排除。

---

## §3 ★ 两个必须提前建立的判断习惯

### 3.1 先分清「业务 403」和「WAF 拦截页」

**在把 403 当成"打不进去"之前，一定先看响应体长什么样。**
亲例：SHEIN 自研 WAF（GSRM Security）的拦截页是固定 2662 字节：

```
<title>Error Page</title> … STATUS:403 / The server's gone missing. / EVENT ID:xxxx / 
Sorry, Please contact GSRM Security support for more information.
```
一旦看到这张页，说明**不是"路径不存在"而是"IP 被拦"** —— 此时所有后续 403 结论全部无效。
（`.git/config`、`/actuator/*` 这类路径返 2662 而不是 404，就是被 WAF 按规则拦了。）

### 3.2 枚举前先估算封禁阈值，被拦了就用「低频浏览器探针」

**反面亲例**：259 条正常探活 + 60 次 actuator/nginx 探测**都没触发**；
随后用 **Python 脚本裸打** `seal.sheincorp.cn` 的 ~16 个 WebLogic 路径 + 1 次 T3 握手 → **出口 IP 被全域拉黑**（跨域生效）。

**正面亲例（同一目标，换 IP 后）**：改用 `agent-browser-cli（低频探针）`，**30 个请求分布 6 个主机，零封禁**。
→ 说明这类 WAF 主要看**请求特征 + 速率**，不只看次数。

#### 工具：`agent-browser-cli（低频探针）`（低频浏览器内探针）

原理：**不在 Python 里裸打**，而是在**真实 Chrome 的页面上下文里用 `fetch`** 逐个取路径 ——
浏览器自带真实 TLS 指纹/JA3、`Sec-Fetch-*`、`Referer`、Cookie 与 JS 执行环境，没有"脚本特征"。

```bash
PY312="C:/Program Files/Python312/python.exe"
cd E:/codex_work/ravenholt_渗透/agent-browser-cli
"$PY312" cdp.py open "https://target/" --key target --port 9888      # 先建立正常访问轨迹
CDP_PORT=9888 "$PY312" cdp_slow.py "https://target/" /a /b /c --dmin 6000 --dmax 12000
# 多主机：CDP_PORT=9888 "$PY312" cdp_slow.py --plan plan.json --out result.json
```

四个要点：
1. **先 `Page.navigate` 到目标根域名**再 fetch（否则跨域 CORS 直接失败，表现为 `TypeError: Failed to fetch` 且耗时 0~1ms）；
2. 路径间随机 `sleep 6~12s`，跨主机再等 5~6s；
3. **内置拦截页熔断**：命中 `GSRM Security` / `The server's gone missing` / `EVENT ID:` 立刻终止剩余请求；
4. `ping` 到 `--dmin 0` 就是普通并发探针，别拿它扫端口。

#### 其余操作纪律

- 单主机异常路径枚举 **≤10 次/分钟**，总量控制 15 次以内；
- 一发现 403 拦截页立刻停手，换 host 或换 IP；
- 被拦了要**主动告诉用户**（含拦截页里的 EVENT ID），而不是当成"不可访问"糊过去；
- **别把 403 当排除依据**：nginx 阶段顺序是 `server-rewrite`（脆弱代码在这）→ … → `access`（`deny all` 返回 403），
  **403 是 rewrite 之后才产生的** → 全站 403 的站必须按"未排除"处理。

---

## §4 交付物结构（n-day 报告）

1. **结论速览表**（组件 | 主机数 | 版本是否在范围 | 实测可打性 | 定级）
2. **⚠️ 操作风险**（是否触发封禁、拦截页特征、应对）
3. **指纹真伪核实**（误报清单 + 证据 + 真实指纹清单）——**这节最容易被跳过，但最有价值**
4. 逐组件判定明细（含每条探测的实测状态码与响应片段）
5. **误报指纹剔除清单**（给后续复用的人，避免重踩）
6. 非 n-day 但值得记的信息泄露（网关头泄漏内部 app 名、CI_COMMIT_SHA 等）
7. **复核清单**（哪些必须到主本机/内网才能定论，给出具体命令）

### 顺带薅出来的高价值情报（别漏）

- **自研网关泄漏内部 CMDB 标识**：`header-cmdb-app-name` / `header-cmdb-name` / `via-shein-gateway`
  → 直接给出内部应用名 + 环境（`elkFront`、`gmpFront`、`csrp_sub_front`、`eyjafjalla`…）→ **内网测绘金矿**
- **前端配置明文泄漏 Git commit**：`window.<x>_env_config['CI_COMMIT_SHA']='...'` → 定位源码版本
- 响应头 `x-api-gateway-version`、`x-apisix-upstream-status`、`x-oss-cdn-auth` → 判断网关型号与链路

---

## §5 组件专属「只读指纹 oracle」（2026-09-18 乐信实测补充）

> 目标：**不改动任何东西、不触发任何利用**，拿到组件的**类别与版本**。
> 本节的 oracle 全部是「静态资源存在性」或「标准虚拟目录响应码」，零副作用。

### 5.1 Microsoft Exchange —— 只看 4 个头 + 一张端点矩阵表

| 证据 | 值 | 说明 |
|---|---|---|
| `Server` | `Microsoft-IIS/8.5` | ★ **IIS 8.5 = 宿主 Windows Server 2012 R2** ⇒ Exchange 只可能是 **2013 或 2016**（2019 需要 WS2019/IIS 10） |
| `X-FEServer` | 如 `SZL-CAS-02` | ★ **Exchange 专属头**，同时泄漏 CAS 主机名 |
| `X-Powered-By` | `ASP.NET` | 辅助 |
| `X-OWA-Version` | `15.0.1497.xx` | ★★ **唯一干净的精确版本 oracle**，但只在 OWA 响应上出现 |

**端点矩阵（全 GET）**：

| 路径 | 正常响应 | 含义 |
|---|---|---|
| `/owa/`、`/ecp/` | 302 → `/owa/auth/logon.aspx` 或 200 | OWA/ECP 对外可达 |
| `/EWS/Exchange.asmx` | **401 + `WWW-Authenticate: NTLM`** | ★ EWS 存活 |
| `/mapi/` | **401 + NTLM** | ★ MAPI/HTTP 存活 |
| `/autodiscover/autodiscover.xml` | 401 + `Basic realm="…"` | Autodiscover 存活 |
| `/Microsoft-Server-ActiveSync` | 401 + Basic | ActiveSync 存活 |
| `/rpc/` | 401 + Basic | RPC/HTTP 存活 |

**乐信实测（亲例）**：`/owa/`、`/ecp/`、`/owa/auth/logon.aspx` 全部 **403**，但响应体是 **IIS 本地化的标准 403 页**
（`<title>403 - 禁止访问: 访问被拒绝。</title>`，GBK，1157B）⇒ **OWA/ECP 是在 IIS 层被 deny 的**（有意只放协议端点）；
而 `/EWS`、`/mapi`、`/rpc`、`/autodiscover`、`/ActiveSync` 全部 401 存活。

★★ **两条必须写进结论的话**：
1. **「EWS/MAPI 对外可达」是 ProxyShell(CVE-2021-34473/34523/31207)、ProxyLogon(CVE-2021-26855)、
   ProxyNotShell(CVE-2022-41040/41082) 的必要前置面 —— 但「可达 ≠ 未打补丁」，不能据此定级。**
2. OWA/ECP 被 deny ⇒ **取不到 `X-OWA-Version` ⇒ 构建号无法只读确认** ⇒ 定性**只能**落到主机侧：
   `Get-ExchangeServer | fl Name,Edition,AdminDisplayVersion`、`Get-Command Exsetup | %{$_.FileVersionInfo}`。
   **不要为了拿版本去试 Host 头变形 / `X-BEResource`** —— 那已经是绕过控制、属利用尝试。

**怎么分清「IIS 403」与「WAF 拦截页」**：IIS 403 页是**完整 HTML 模板 + 本地化文案**（`403 - 禁止访问: 访问被拒绝。`），
WAF 拦截页通常是固定小体积 + 厂商标识（`GSRM Security`、`EVENT ID:`）或 `Request Rejected`。**先看体积与模板再下结论。**

### 5.2 Drupal —— Generator meta + 主题静态资源存在性（完全零副作用）

1. **主版本**：触发任意 404 → 404 页 HTML 里
   `<meta name="Generator" content="Drupal 10 (https://www.drupal.org)" />` ⇒ 直接给出主版本。
   （Drupal 7 也会输出 Generator meta；Drupal 8/9 默认不输出，但 D10 输出。）
2. **主版本交叉验证（主题资源存在性）**：请求 `/core/themes/<主题>/logo.svg`

   | 主题 | 引入 | 移除 | 判读 |
   |---|---|---|---|
   | `olivero` | 9.1（9.3+ 默认前端主题） | — | 200 ⇒ ≥9.1 |
   | `claro` | 8.8（9.0+ 默认管理主题） | — | 200 ⇒ ≥8.8 |
   | `seven` | 8.x 默认管理主题 | **Drupal 10 移除** | **404 ⇒ 排除 D8/D9** |
   | `bartik` | 8.x 默认前端主题 | **Drupal 10 移除** | **404 ⇒ 排除 D8/D9** |
3. **辅助**：`/core/misc/drupal.js` 200（D8+）、`/core/COPYRIGHT.txt` 200、`/robots.txt` 为 Drupal 默认模板、
   `X-Drupal-Dynamic-Cache` 响应头。
4. **minor/patch 通常拿不到** ⇒ **主版本 = 10 已经排除了 Drupal 历史上最凶的 RCE 家族**
   （Drupalgeddon1 CVE-2014-3704 打 7.x；Drupalgeddon2 CVE-2018-7600 / 3 CVE-2018-7602 打 7.x 与 8.3.0–8.5.0）
   —— **这是"主版本确认"能带来的实际收窄，值得单独写一句结论。**
   minor 只能主机侧 `drush status` / `composer show drupal/core`。

### 5.3 Tomcat —— 版本从 404 页页脚白送，AJP 用单次 TCP connect 判

- **版本**：Tomcat 默认 404 页页脚即 `<h3>Apache Tomcat/8.5.50</h3>` —— 一个 `GET /任意不存在路径` 就能拿到精确版本。
  （乐信亲例：`esign.lexin.com` → 8.5.50；`datashare.lexin.com` 的 `/kapi/` → 9.0.45。）
- **Ghostcat 判定（CVE-2020-1938）**：**只要 AJP 8009 不开放，该 CVE 直接硬性排除**。
  判法 = **单次 TCP `connect()`，不发任何数据、不握手**（零副作用）→ `CLOSED(TimeoutError)` 即可下结论。
- **管理面**：`/manager/html`、`/host-manager/html`、`/docs/`、`/examples/` 一律 `GET` 判存在（404 = 未部署）。
- **CVE-2025-24813 / CVE-2020-9484** 需要 **default servlet `readonly=false`**（Tomcat **默认 `true`**）+
  会话持久化 / 写能力 ⇒ **验证必然要发 `PUT`（写操作）⇒ 不在只读轮做**，只能在主机侧看 `conf/web.xml`。
- **CVE-2020-13935（WebSocket DoS）一类**：**只能崩，属 DoS 红线，不验证。**

### 5.4 Tengine / OpenResty / nginx —— 「无法确认」也是一种结论

- `Server: Tengine` / `Server: openresty` **都不带版本号** ⇒ CVE-2026-42945 的**版本层无法判定**。
- 安全排除法（见 §2）在**业务站上往往不成立**：乐信 `www.lexin.com` 对**任意路径**都返
  **200 + 同一份 1300B 自定义"迷路了"兜底页**（`/index.php` 也 200）⇒ 既不是「静态自定义 404」，也不是标准 catch-all 404，
  **三条件未全满足 ⇒ 不能据此排除**。
- ⇒ 结论只能写成两级：**版本层未知 + 配置层无法远程判定**，落到主机侧
  `nginx -V` + `grep -rnE 'rewrite[^;]*\?[^;]*;' <conf_dir>/`。
- ★ **崩溃式探针（`GET /<prefix>A*349+*969`）属 DoS，没有明确授权一律不做**；本任务历史上该 CVE 亦为「未复现」。

### 5.5 对象存储 —— 三种列举全非 `ListBucketResult` 即排除

`GET /`、`GET /?list-type=2&max-keys=1`、`GET /?prefix=&max-keys=1`。
乐信亲例：`coss-ec`/`coss-smart` 返 `404 Not Found`；`coss-ad` 返 2 字节 `OK`（阿里 ESA）
⇒ **都不是 bucket 端点，直接排除**（别因为域名里带 `coss`/`oss` 就当对象存储）。

---

## §6 ★ 误报的第三种形态：**网关 / SPA catch-all**（比 §1 的关键词型更隐蔽）

§1 讲的误报是「**关键词**碰巧出现在响应里」。这里补一种**响应码型**误报 ——
**路径返回 200，但服务端根本没消费路径**。

**判定铁律：对同一个 host 打 ≥3 个语义完全不同的路径（`/actuator`、`/env`、`/swagger-ui.html`、`/robots.txt`、`/zzz`），
看是否返回「状态码 + 长度 + 正文**逐字节相同**」的响应。是 ⇒ catch-all，全部作废。**

乐信实测（亲例）：

| host | 现象 | 结论 |
|---|---|---|
| `api.fenqile.com` | `/actuator`、`/actuator/health`、`/env`、`/health`、`/swagger-ui.html`、`/v2/api-docs`、`/swagger-resources` —— **7 个路径全返同一个 45B JSON** `{"result":10200004,"res_info":"url不存在"}` | 网关 catch-all ⇒ **Actuator/Swagger 全为误报** |
| `openmoa.oa.fenqile.com` | 5 个路径全返 45B `{"retmsg":"无效的 url","retcode":30281014}` | 同上 |
| `open.fenqile.com` | 6 个路径全返 **7183B** SPA 外壳 | 同上（SPA 兜底） |
| `cloudapi.dszc-amc.com` | 路径返 404，但 **404 页把请求 URL 回显进正文**（`URL: http://…/actuator`）⇒ 扫关键词时命中 "actuator" | ★ **§1 的关键词型误报 + URL 回显叠加**；换任意词同样被回显 |
| `api-unifygateway.dszc-amc.com` | 任意路径返 51B `{"code":"002001","msg":"非法参数"}` | 同上 |

**顺带正面价值**：这类 catch-all 响应本身就是**未鉴权可达的网关错误码字典**
（`10200004`、`002001`、`30281014`），摸清语义对后续参数枚举有用。

---

## §7 ★ 操作风险：**Akamai 前置目标的枚举阈值极低**（2026-09-18 亲例）

- **现象**：对 `ir.lexin.com`（Akamai + EdgeConnect 前置）累计约 **20 次只读 GET**（做 Drupal 版本 oracle）后，
  该 host 对本次出口 IP **全路径 403**（`/`、`/robots.txt` 都 403；而此前 `robots.txt` 是 200）。
- **关键鉴别**：**同一时刻其它乐信资产（`www.lexin.com` 等）仍正常 200** ⇒ 是**按 host 的速率/机器人限制**，
  **不是全域 IP 封禁**（对比 §3.2 里 SHEIN 的「跨域全域拉黑」是另一种模式）。
- **教训**：
  1. 见到某 host **突然全路径 403**（尤其此前访问过 200），**先怀疑自己被按 host 限流**，
     别当成「目标本身配置成 403」写进结论。
  2. 对 **CDN/Akamai 前置**的目标，路径枚举预算要**比自研 WAF 更保守**（本亲例 ~20 次即触发）。
     版本 oracle 类探测一次做**一个 host**，做完就换。
  3. 被拦后**如实告诉用户**（哪个 host、累计多少次、影响哪个结论），不要用"连接失败"糊过去。
  4. 一个 host 被限流时，**不要换个 UA/加 header 硬顶** —— 那是加重特征，且越顶越久。

---

## §8 交付物结构（n-day 报告）—— 本节已并入上方，此处保持编号连续

---

## §9 ★★ 理想汽车 533 host 实测补充（2026-09-21）：四类新情况

> 场景：用户给一份子域清单说「**存活的网站都打 n-day**」。
> 本节回答一个 §1~§7 没覆盖的问题：**「都打」什么时候是无效劳动**，以及怎么把无效劳动
> 变成**有证据的结论**而不是硬打。

### 9.1 ★★ 自研网关封装开源组件 —— 组件指纹真，但 CVE 面不存在

**现象**：TscanPlus 报 `Apache APISIX` × 26，但实测 `Server: LiFE`（理想自研名），
响应体确为 APISIX 原生 `{"error_msg":"404 Route Not Found"}` ⇒ **组件指纹是真的**。

**判据（三步，全只读）**：
```
GET /apisix/admin/routes                                    # 无 key
GET /apisix/admin/routes  -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1'   # CVE-2020-13945 默认密钥
GET /apisix/dashboard/                                      # CVE-2021-45232
```
**26/26 全部返回同一个 36B `404 Route Not Found`（含默认密钥场景）⇒ admin 面未挂公网 ⇒ 两条 CVE 均不可达。**

★ **关键认识**：**自研二次开发（改了 `Server`、未挂 admin）不改变组件识别，但直接消灭了该组件的 CVE 可达性**。
所以「命中 APISIX 指纹」≠「可打 APISIX CVE」，**必须实测 admin 面在不在**。
同理适用于 `openstar system`（理想另一代网关，同样恒返网关响应）。

### 9.2 ★★ 「恒返同一响应」的第二种用途：不是误报，是**该面不可判定**的证据

§6 讲的是 catch-all 导致**误报**（把不存在的端点判成存在）。
这里补它的**反面用法** —— 它同时证明**这个面无法用路径探测判定**，于是「都打」是无效的：

| 亲例 | 实测 | 结论 |
|---|---|---|
| **167 个 `Server: LiFE` 网关 host** | **任意路径**（`/`、`/nacos/`、`/.env`、随机串、n-day 路径）**恒返同一个 36B `404 Route Not Found`** | 未配置路由不转发 ⇒ **打任何 n-day 路径都无差分** ⇒ 对这批 host 的 200+ 次扫描**必然全是噪声** |
| `s-elearning.lixiang.com` | 任意路径 200 + 同一 SPA 壳 | 该 host 除 WAF 403 外**结论全部作废** |

⇒ **交付写法**：不要写「已扫描 200 个 host 未发现漏洞」（那是虚假进度），
要写「**167 个 host 为网关且对任意路径恒返同一响应 ⇒ 该面用路径探测不可判定；可判定面仅 ~40 个非网关直连 host，已按指纹分组覆盖**」。
**这比盲打 1000 次请求更接近真相，且能省下被封禁的风险。**

### 9.3 WAF 拦截页的**两种形态** + 大小写绕过的**边界陷阱**

理想自研 `chj-Waf`（LX-WAF）实测两种命中形态，**都可当指纹**：

```
403 + 16 字节纯文本：deny by chj-Waf                      # 应用前置式
403 + ~2.5KB 中文 HTML 拦截页（lang=zh-CN，「您提交的信息对网站可能造成威胁」）
```

**WAF 覆盖实测**（3 个代表 host，同样路径）：`.git/config`、`swagger-ui.html`、`druid/index.html`、
`v2/api-docs` **全 403**；但 **`/nacos/` 与 `gns.chehejia.com` 的 `/.env` 未被拦**（返应用 404）
⇒ **规则不是全覆盖** ⇒ 结论必须写「**被规则挡住 = 未测定**」，**不是「打不进去」**（呼应 §3.1）。

★ **边界陷阱（亲例）**：`/ACTUATOR/health` **成功绕过**了 WAF（规则大小写敏感），
**但 Spring 的端点路径也大小写敏感** ⇒ 绕过之后仍返 404 ⇒ **拿到的是"未启用"这个真结论**。
⇒ 教训：**绕 WAF 前先想清楚"绕过了下游能不能消费"**（同 SKILL §2 第 9 条的精读），
这里下游可消费（能区分启用/未启用）⇒ 绕得值；如果下游本身大小写不敏感但 WAF 也拦变体，就没必要硬顶。

### 9.4 自研签名头的识别（容易当成漏洞）

`sec-ys-cmd.chehejia.com`：`/index.php` → `403 {"code":403,"message":"miss required header X-HMAC-ALGORITHM"}`。
**这不是 WAF，是应用层的自研 HMAC 签名闸** ⇒ 属「未授权面」而非 n-day；
它的价值是**告知了鉴权头名称**，应进「信息泄漏」而非 n-day 明细。

### 9.5 顺带情报（写进报告，别漏）

- **WAF 精确版本外露**：`Server: LX-WAF 2.3.5 / 2.3.3 / 2.3.0 / 2.2.13 / 2.3.X`（14 host）。
- **多云 + 区域拓扑全泄漏**（最强的一条）：`bcs-life-apisix-dp-{ali|aws|bidu|vol}-{common|vehicle}-public-{cnhb|cnhz|cnsz|cngz|cnsh}[-{云商}-lb]`
  ⇒ 直接暴露 **阿里云/AWS/百度云/火山引擎四云、五地、数据面(DP)节点**。
  **这类命名规范泄漏与 §4 的 `header-cmdb-app-name` 同类，但更结构化** —— 见到 `*-dp-*`、`*-lb`、
  云商缩写（`ali`/`aws`/`bidu`/`vol`）要专门抄下来。
- 对象存储端点识别：`{"locationConstraint":"bj"}` = S3 `GetBucketLocation` 响应；
  404 带 `{"code":"NoSuchKey",…,"requestId":…}` = 自研 S3 兼容端点。**但列举三枪仍是唯一判据**。

### 9.6 本轮请求预算（可直接引用）

约 **250 次只读 GET / 60+ host / 单 host ≤12 次 / 间隔 1.1~1.6s** ⇒ **零封禁、零限流页**。
对照 §3.2 的反面亲例（Python 裸打 16 次即被全域拉黑）—— **「分得散 + 间隔够」比「打得少」更关键**。

---

## §10 ★★ 第二轮补充（2026-09-21 理想续）：**重采完整响应头**是必须的一步

> 教训：第一轮只用了「探活时落盘的 body + 4 个响应头」，指纹只覆盖 10 个 host。
> **重采 201 个非网关主机的完整响应头后，才认出 Laravel × 3 和 Envoy × 2。**
> ⇒ **别只扫 body**：框架与组件的指纹**大量藏在响应头里**。

### 10.1 ★ `Set-Cookie` 是识别服务端框架的高价值来源（本轮最强的一条）

| Cookie 名/值格式 | 框架 | 判据 |
|---|---|---|
| **`laravel_session=eyJpdiI6…`** | **Laravel** | 值 = base64 of `{"iv":"…","value":"…","mac":"…","tag":""}` ⇒ **`eyJpdiI6`（`{"iv":"`）是 Laravel 加密载荷的固定前缀**。★ 自定义 cookie 名（如 `chehejia_okr_session`）**改不掉这个值格式** ⇒ 换个名字照样能认 |
| `PHPSESSID` | PHP | — |
| `JSESSIONID` | Java/Tomcat | — |
| `ASP.NET_SessionId` / `__RequestVerificationToken` | ASP.NET | 后者是 MVC 防伪令牌 |
| `_session_id` + `X-Runtime` | Rails | — |
| `XSRF-TOKEN` | Laravel / Spring | — |
| `acw_tc` / `aliyungf_tc` | **阿里云 WAF / 阿里云函数** | 说明前置是阿里云 |
| `BAIDUID` | 百度（前置 CDN/云加速） | — |

**做法**：重采时把 **全部响应头** 落盘（别只留白名单），再按上表过一遍。
亲例：`coa-api.lixiangoa.com` 的 `Set-Cookie` 直接暴露 `laravel_session` ⇒ 才知道要去打 CVE-2021-3129。

### 10.2 Laravel Ignition（CVE-2021-3129）判定的**三态**，别只记两态

```
GET /_ignition/health-check      # + 一条基线 GET /zz_nope_<rand>.txt
```
| 结果 | 判定 |
|---|---|
| **404**（且与基线 404 同体积同内容） | **路由不存在 ⇒ 不可达** ⇒ 收工 |
| **200 但等于基线**（任意路径同响应） | **catch-all ⇒ 零差分 ⇒ 不可判定**（本轮 `user-center-api` 即此态） |
| 200 + `{"can_execute_commands":true}` / `{"status":"ok"}` 且**不等于基线** | **Ignition 活着** ⇒ 进零写入验补丁法（`zz_nope.txt` vs `zz_nope.blade.php`） |

★ 注意 `/_ignition/execute-solution` 可能被 **WAF 单独拦（403）**，不代表该站没有 Ignition ⇒ **必须用 `health-check` + 基线对照判**。
★ **写链（清日志→投毒→`phar://`）属破坏性，未获服务端授权一律不碰** —— 只做零写入判定。

### 10.3 ★★ 自研网关头批量泄漏内网后端：把「响应头」当测绘面来扫

亲例：**78 个 host** 的响应头带 `x-chj-routeurl: http://<内网IP>:<端口>/` —— 逐个抄下来就是**内网服务全图**：

| 泄漏 | 例 |
|---|---|
| 内网 IP:PORT | `172.21.27.229:10978`、`10.60.4.117:10981`、`172.21.27.230:10980` |
| **K8s + 云厂商内部域名** | `k8s-cnbj02pr-bcsjedia-<hash>.elb.cn-north-1.amazonaws.com.cn:10978` ⇒ **一次泄漏集群名 + 工作负载名 + 区域** |

**同类头名（见到就抄）**：`x-chj-routeurl`（理想）、`X-CHJ-RouteUrl`、`header-cmdb-app-name`（SHEIN）、
`x-proxy-route-path` / `-code`、`via`（字节 NSS 的 `via=n111-020-021-253`）、`x-envoy-upstream-service-time`（Envoy 在链路里）。
**做法**：重采头时**不要只留 server/ct/ck**，把这些也留 —— 它们往往比 n-day 更有报告价值。

### 10.4 「无公开 CVE」与「CVE 全是 DoS」也是结论

- **Kibo Commerce**：SaaS 商业平台，**检索后确认无公开 CVE** ⇒ 无线索，写进交付即可（别硬凑）。
- **Kestrel / ASP.NET Core**：相关 CVE（CVE-2023-38180、CVE-2026-42899、CVE-2026-40381）**全是 DoS 类**
  ⇒ **按绝对红线一律不做**，在报告里写「已知 CVE 均为 DoS，按红线未验证」。
  ★ 这一条能挡掉大量「看到 .NET 就想打」的冲动。
- **Bytedance NSS**（字节流媒体推拉流，`Server: Bytedance NSS`，返 `400` + `via=...`）：无线索。
- **Envoy**：作为数据面出现（`x-envoy-upstream-service-time`），本身不是漏洞面。

---

## §11 「`wp-` 字样 ≠ WordPress」+ 国产站群 CMS 识别（2026-09-26 亲例）

> 触发：用户说「这些站好像都有 WordPress，去 GitHub 看最新 WP 漏洞全部测一遍」。
> **先证伪再动手** —— 本轮证伪成功，省掉整轮无效工作。

### 11.1 WP 独有命名 ≠ WP 存在（六项独立否定）

`wp-content/uploads/sites/NN/`（多站点 blog id）、`wp-polyfill.min.js`、`pagenavi-css.css`、
主题位 `wp-content/themes/school_<校>_<单位>/` —— **全是 WP 独有命名，极易判成 WP**；
`<meta name="generator" content="站点名 5.8.6 - https://host">` 也像版本号（**WP 没有 5.8.6**）。

**六项独立否定（成本极低，先做）**：

| # | 请求 | 有 WP 时应为 | 亲例实测 |
|---|---|---|---|
| 1 | `GET /wp-login.php` | 200 登录页 | 子站 `404`(3B) / 主站兜底首页 |
| 2 | `GET /wp-json/` | 200 REST 索引 | 404 / 兜底 |
| 3 | `GET /readme.html`、`/feed/`、`/xmlrpc.php` | 200 | 404 / 兜底 |
| 4 | `GET /wp-includes/js/wp-emoji-release.min.js` | 200 JS | 返回 HTML（兜底） |
| 5 | **首页真实引用的** `wp-content/uploads/…` 图片 | 200 `image/*` | **全部取不到** |
| 6 | `GET /wp-content/plugins/`、`/wp-content/themes/<slug>/` | 目录/文件 | 兜底 / 404 |

★ **决定性反证 = 追那条 `wp-content` 图片 URL 的真实主机** —— 亲例它指向**外站**
`https://www.huatangonline.com/document/wp-content/uploads/…`（**模板厂商自己的 WP 站**）
⇒ `wp-` 是**模板残留 + 厂商命名习惯**，目标机上不存在 WP。

**两个连带坑**：
- ★ **catch-all 会把「不存在」伪装成「200」**：亲例主站任意路径都返首页（长度与 `/` 完全相同）
  ⇒ 对 catch-all 站点做路径探测**全部失真**，必须用**长度/md5 与首页比对**来识别。
- ★ **同一台机可能有两套 404**：静态 `404`（3 字节, iso-8859-1）vs 应用错误页（2288 字节, UTF-8, 引用应用资源）
  ⇒ **可据此判路径到底由哪个后端处理**（亲例 `/cms/**` 走 Java 应用，不受静态兜底影响）。

### 11.2 国产站群 CMS 的识别路径（GitHub 精确串搜索 > 搜索引擎）

1. **页脚隐藏署名**：`<div style='display:none'>Produced By CMS 网站群内容管理系统 publishdate:…</div>`
   （**这是最强的产品级指纹，先 `grep` 页面尾部**）
2. **模板骨架**：`/inc/*.js`（`appvar.js`/`pub.js`/`tree.js`/`flv.js`/`WdatePicker.js`）、`/lib/template/{static,scheme}/`、
   图片真实目录 `/rootimages/YYYY/MM/DD/`（用一张真图片验证它 **200 + `image/*`**，与 `wp-content` 的死路径对比）
3. **★ 最强单点指纹在计数 JS 里**：`dynclicks.js` 的
   `/system/resource/code/news/click/dynclicks.jsp?clickid=..&owner=..&clicktype=..`
   —— 拿**这条精确路径**去 GitHub `search_code`，命中的仓库即暴露产品线（亲例命中多所高校站点。
   再用 `"<署名原文>"` 搜到指纹库规则 `0x727/FingerprintHub` → `合正软件-网站群内容管理系统-hzcms.yaml`，
   `py-whatcms` 的 `conf/hzcms.conf` 给出 `Corp=北京合正软件`、`Platform=java`）
4. **管理端定位**：应用 404 页里引用的资源路径（如 `/cms/cmsadmin/scheme/css/style.css`）反推管理端根
   （亲例 `/cms/cmsadmin/`、登录 `/cms/cmsadmin/wcm/login.jsp`）
5. **效果对比**：本轮 **5 次 WebSearch 全空**（引擎只回泛化内容），**1 次 GitHub `search_code` 即锁定厂商**。
   ⇒ 设备/产品指纹一律优先 GitHub 代码搜索。
6. ★★ **命中后必须先判「命中的是源码，还是字典/指纹库」** —— 亲例两个陷阱：
   - `laoyang103/qdcloud` 仓库里有 `src/main/webapp/system/resource/js/dynclicks.js`，
     看着像产品源码，实则该仓库是个网络运维项目**顺手拷了一份这个文件** ⇒ **与产品无关**；
   - `"cmsadmin/infopub"` / `"webappcode pubtype templetid"` 命中的是
     `boy-hack/wooyun-payload`、`gh0stkey/Web-Fuzzing-Box` 这类 **wordlist / 指纹库** ⇒
     只证明「这条路径是圈内已知爆破目标」，**不提供源码**。
   ⇒ 判据：看命中仓库的**目录结构与文件类型**（真源码应有 `WEB-INF/`、`*.java`、`pom.xml`、
     成片的 `*.jsp`；只有 `.txt` 字典或孤立单个文件 ⇒ 不是源码）。
7. **产品若是商业闭源，就承认拿不到源码**（口径要写清），改去拿**行为面**：
   管理端登录页 HTML（`<title>` 常直接给出产品全名）、真实登录接口（`dologin.jsp` 之类）、
   加密方式与字段名。★ 前端硬编码 RSA 公钥**实值不入档**（见 `03` 手机号加解密钥禁令）。

### 11.3 ★★★ 测搜索/查询接口：必须先从表单 JS 还原「完整提交体」

亲例 HZCMS：`POST /cms/cmsadmin/infopub/search.jsp` 需 **9 个字段**，页面 JS 里
`search(){ frm.keywordencode.value = encodeURI(frm.keyword.value); frm.submit(); }`。

**只传 `keyword`** ⇒ 参数**完全不生效** ⇒ `test` / `test'` / `test''` / `' and 1=1` / `' and 1=2`
**5 种载荷响应逐字节相同** ⇒ 会被误读成「keyword 被忽略 / 无注入」。**这是假阴性，不是结论。**

**正确流程**：
1. 从首页 `grep` 出 `<form>` **完整 HTML**（含全部 `type=hidden`）+ 提交函数体；
2. 按表单**原样**重放，先发**阳性对照**（一个必然有结果的正常词）—— **对照组必须出现可见差分**，
   否则先怀疑自己的请求不对，不许下结论；
3. 再做 `AND '1'='1` / `AND '1'='2` 布尔对、`' OR 1=1-- ` 破出对。

### 11.4 ★★ 「HTTP 500」不等于「SQL 错误」—— 先读响应体

亲例：`keyword=学院' AND '1'='1` → **500**，读体发现是
`java.lang.IllegalArgumentException: URLDecoder: Illegal hex characters in escape (%) pattern`
—— 应用**二次 URL 解码**抛异常，**与数据库无关** ⇒ 这两发**根本没到 SQL 层**，不能判注入。
★ 连带：该回显本身是**低危**（Java 异常原文 + 栈信息泄漏给匿名用户）。

### 11.5 本轮口径与产出（供复用）

- 13 类参数形态全测（`keyword`/`webappcode`/`pubpath`/`templetid`/`pubtype`/`model`/`display`/`relation`），
  布尔对照对**逐字节相同**、`OR 1=1` 无法扩大结果集 ⇒ **未形成注入判据**。
- 口径：写「**未测定 / 未形成判据**」，**不写「无注入」**。
- **`dynclicks.jsp` 是计数自增接口 ⇒ 判为「写操作」，按红线未打**（这不是"漏测"，是纪律）。
- 附带：首页常明文列**内网 IP**（亲例 `172.22.33.181/182/183/141:90`）与**关联系统清单**
  ⇒ 信息级 + 扩面线索，一并入档。

---

## 12. ★★ 「未授权可达」的判据必须做**参数形态矩阵** —— 无参时"没被拦"是假信号

> **一条铁律：servlet 的「免登录」往往只在「参数不全会空转」这个形态下成立。**
> 你看到「无参请求没返回登录跳转、而是返回一个异常页 / 空页」，**不能**读成「该端点未校验会话」——
> 它可能只是**什么都没做**。真正的敏感逻辑与**它的会话闸**一起，挂在**特定参数组合**上。

**亲例（2026-09-26，致远 OA A8 / V8.1SP2 / build `V8_1SP2_230116_1705092`）**
`/seeyon/m-signature/RunSignature/run/getAjaxDataServlet`（QVD-2023-30027 前台 XXE 的入口）：

| 形态 | 响应 |
|---|---|
| 无参 / 只有 `xmlValue` / 只有 `S` / 只有 `M` / 只有 `method` | `200 / 373B` 同一异常页（**什么都没发生**） |
| **`S` 与 `M` 同时存在**（**任意取值**） | `200 / 58B` 同一「`[LOGOUT]`被迫下线」 |

⇒ 我上一轮把第一列读成「**未校验会话**」是**错的**：那是**空转**，不是免鉴权。
加上 `S`+`M` 后，闸立刻生效；而且**畸形 XML 与合法 XML 的响应 sha 完全一致** ⇒ **鉴权先于解析**，
XXE 载荷**根本没进解析器**（内实体标记也未反射）。

**做法（每个 servlet / handler 都要过一遍）**
1. 先取**无参基线**，再逐级加参数：`无参 → 单参 → 双参 → 全参 → 畸形值`。
   **分岔点出现在哪一级，闸就在那一级。**
2. **参数取值也要变**：垃圾值 / 只读方法名 / PoC 原值 —— 若三者响应 sha 全同，
   说明**分发在解析 manager 之前就被拦**（本亲例如此）。
3. **判「闸要的是什么」**：先 GET 一次登录页拿到**真实下发的匿名 cookie**，再带它打 → 仍被拦
   ⇒ 闸要的是**登录态**，不是「有没有 cookie」。这一步把"缺 cookie"与"缺权限"分开。
4. **判顺序**：把载荷换成**畸形格式**打一发。响应仍是同一拦截页 ⇒ **鉴权在前、解析在后**；
   响应变成解析错误 ⇒ 解析在前（那是可以继续挖的形态）。

## 13. ★★ 「响应 sha 坍缩法」—— 一批探针坍缩成 N 个 sha，判据就硬了

一大串探针（亲例 **28 发**）如果响应**坍缩成少数几个 sha**，结论比"逐个看长度"硬得多：

- **坍缩得越干净，分岔点越少、结论越硬**。本亲例 28 发只坍缩成 **3 类**：
  `373B/异常页`、`58B/[LOGOUT]`、`404/537B`。
- **坍缩点即判据**：能区分这 N 类的**唯一变量**就是根因（本亲例 = `S` 与 `M` 是否同时存在）。
- ★ **务必比对整个 raw body 的 sha，不要只比长度**。长度相同 ≠ 内容相同；
  长度不同也可能只是**动态时间戳**，取 sha 前先看有没有噪声字段。
- ★ **把原始响应体全部落盘**（本亲例 `xxe/*.html` + `results.json`），
  结论句可以在报告里被逐条回测，这是"承重句回测"纪律的落地方式。

## 14. ★ 「完整原样打一发公开 PoC」是收口的必要动作

即使已用**替代形态**证明了"打不通"，也应当**把公开 PoC 原样打一发**（守红线前提下）：

- 它排除掉「是不是我少传了某个参数 / 用了错的 M」这种质疑 —— 本亲例打出的是**同一个 58B sha**；
- 它顺带**证明写语义方法未被调用**（亲例 `colManager.colDelLock` 在鉴权前即被拦，
  ⇒ 用户担心的"释放编辑锁"副作用**在本目标不存在**）；
- 口径仍只写「**公开 PoC 常量未复现**」，**不写「已打补丁」**（常量失效与补丁不可区分，见 §11.5 同理）。

---

## 15. ★★ 上下文路径拼写 —— 「静默空 404」是假 404 的最隐蔽一种

判「路径/端点不存在」之前，**必须先确认上下文路径（ctxPath）的拼写**。

**亲例（2026-09-26，`oa.cdcas.com` 致远 OA）**：产品 ctxPath 是 **`/seeyon`（两个 e）**，
我因从 GitHub 文档转抄时把 ee 抄成 ey，写成 **`/seyeon`**，结果得到：

```
HTTP/1.1 404
Content-Length: 0
Server: nginx
```

——**没有 body、没有提示、没有 `404 Not Found` 页面**，与「路径真的不存在」的
**`404 / 537B / 404 Not Found`** 长得完全不同，但都叫 404。两轮脚本结果因此全部作废。

**做法**：
1. 从**页面 HTML 里出现的静态资源 URL**取 ctxPath（亲例：`/seeyon/common/all-min.css?V=…`），
   不要从别人的文档/文章里抄路径 —— **别人的文档里也可能有错，或者抄的人会抄错**。
2. **做一次对撞**：`/<正确拼写>/index.jsp` vs `/<错误拼写>/index.jsp`。
   ★ 更强的判据：**同一个路径换个前缀，若一个 200、一个 404/0B，那就是拼写问题，不是端点不存在。**
3. **把 404 分型记进产品档案**（亲例致远 OA）：
   | 形态 | 含义 |
   |---|---|
   | `404 / <产品404页大小>` | **应用级 404**，路径大概率真不存在 |
   | **`404 / 0B` + `Server: nginx`** | **前缀/路由层 404** —— 先怀疑**自己路径写错了** |

★ 同类教训（本知识库已有）：**「先还原 baseURL，只看 path 会产生假 404」** —— 本条是它的
**「basePath 也要还原」**版本。

---

## 16. 致远 OA（Seeyon A8）产品速记 + 漏洞面（2026-09-26 实测）

**指纹**
- `<title>数字化在线办公系统 V8.xSPx</title>`；ctxPath `/seeyon`；A8 分支
  （`/seeyon/common/images/A8/favicon.ico`）
- ★ **构建号零门槛泄漏**：所有静态资源带 `?V=V8_1SP2_230116_1705092`（＝`V8.1SP2` + 2023-01-16）
- **未授权版本探测口**：`GET /mobile_portal/api/verification/checkEnv`

**四种响应指纹（判「存在 / 需登录 / 不存在」极快）**
| 响应 | 含义 |
|---|---|
| `*.do`/`*.jsp`/受保护 servlet 未登录 → **450B** `alert("被迫下线，原因：与服务器失去连接")` | **存在 + 有会话闸** |
| `/rest/*` 未登录 → **401** `{"code":"1010","success":false,...}` | REST 需会话 |
| ajax 网关（`managerName=`）→ **12B** `"__LOGOUT"` | 网关需会话 |
| 参数不全的 ajax 分发 → **373B**「异常处理页面 … 提示信息： null」 | **空转，不是「免鉴权」**（见 §12） |

**架构（web.xml，来源 ax1sX/SecurityList `Java_OA/SeeyonAudit.md`）**
- `CTPSecurityFilter` 覆盖 `*.do|*.jsp|*.jspx|*.psml|/rest/*|/webOffice/*|/services/*|/getAjaxDataServlet`
  以及 `/htmlofficeservlet|/wpsAssistServlet|/pdfservlet|/ofdServlet|/sursenServlet|/m-signature/*|…`
- **`/rest/authentication/ucpcLogin/*` 是 RestFilter 唯一的免检路径**
- **`AJAXDataServlet` = `/getAjaxDataServlet`**：`S`=bean（162 个）/`M`=方法/**参数位 `P_1_String`/`P_2_String`**/`RVT`=返回类型 →
  **反射调用**；★ **S/M 一分不发就空转（373B），S/M 一齐出现就撞会话闸（58B）**
- 有会话时的接口金矿：**`/seeyon/ajaxStub.js`**（RJS 网关描述表，~340KB，
  亲例解析出 **505 个 Manager / 3935 个方法**）

**公开漏洞面（按「载体是否存活」分类，实测于 V8.1SP2）**
- **载体不存在（404）**：`htmlofficeservlet`、`pdfservlet`、`ofdServlet`、`sursenServlet`、
  `isignaturehtml(servlet|H5servlet)`、`office/cache/*`、`logs/*.log`、`management/status.jsp`、
  `wpsAssistServlet`（含 **CVE-2025-34040**）、帆软 `ReportServer`（组件未装）
- **存在但被闸拦**：`webmail.do?method=doDownloadAtt`（**CNVD-2020-62422** 任意文件下载）、
  `ajax.do?…managerMethod=saveFormula4Cloud`（上传 / **JNDI 注入**）、`/rest/m3/common/system/properties`
- **写操作红线洞（勿擅动）**：`POST /seyon/rest/phoneLogin/phoneCode/resetPassword`（**影响版本含 V8.1-SP2**）、
  `PUT /rest/orgMember/<id>/password/share.do` → `POST /rest/authentication/ucpcLogin`、
  `POST /seyon/autoinstall.do/../../seyon/fileUpload.do?method=processUpload`
- **明令防护**：M3 两步反序列化 RCE 的两个路径被单独拦（`404/123B`「访问路径带有 /mobile_portal 无法访问…去掉mobile_portal」）
- ★ **矩阵参数绕过（`;x=1`、`;Jsessionid=`、`autoinstall.do.css/..;/`）在 nginx + V8.1SP2 上全部失效** ——
  别把老 exp 的绕过手法当既成事实，**必须实测**。

---

## 17. ★★ 拿到「真实 web.xml」= 补面效率断层领先（含 3 条派生判据）

**来源**：GitHub 上有**真实客户部署的致远源码仓库** —— `zhanght86/seeyon_v3x`（`WebContent/WEB-INF/web.xml`）、
`passwa11/seeyon-A8-code`（多家高校/开发区的 seeyon 目录含 `WEB-INF/web.xml`）。
**找法**：`search_code` 查 `<特有的一个 servlet 名/init-param 值> filename:web.xml`
（亲例查 `configObtain filename:web.xml` 直接命中 11 个真实 web.xml）。

**为什么强**：一轮就把**全部 servlet 映射**拿到手（亲例致远 A8：`/getAjaxDataServlet`、`/getAJAXMessageServlet`、
`/pdfservlet`、`/htmlofficeservlet`、`/isignaturehtmlservlet`、`axis2=/axis2/*|/services/*`、
`downloadService=/services/downloadService`、`/login/logout`、`/login/proxy`、`/login/sso`、`*.psml`、
`/longPollingWaitServlet`、`/displayChart`(jfreechart)、`/XSLView`、`/FormImgView`、
`/servlet/SeeyonMobileBrokerServlet`、`/servlet/SeeyonMobileAttachmentService`、`xfire=/service/*`），
外加**过滤器覆盖清单**（`GenericFilter` 还覆盖 `/logs/*`）。
亲例一轮 14 发：**13 个当场排除（未映射）**，只有 1 个活 ⇒ 比猜路径、比字典爆破准得多。

**派生判据 ①：产品跨版本，web.xml 里的 servlet 名可能已撤** —— 亲例 web.xml 里有的
`/officeservlet`、`/displayChart`、`/XSLView`、`/login/proxy`、`/servlet/SeeyonMobile*` **在本 build 全 404**。
⇒ **web.xml 给的是"候选清单"，不是"存在证明"**，仍须逐条实测。

**派生判据 ②：★★ 「正则剥掉标签后读报文」会骗你。**
亲例：`thirdpartyController.do?method=access` 返回 4263B 的**渲染页**，我用
`re.sub(r"<[^>]+>", " ", body)` 去标签后只剩尾部碎片（因为开头的 HTML 注释 `<[^>]+>` 一口气吞掉了它后面的内容），
于是**误判成"异常页"**，进而把一个真实存在的第三方接入页当成噪音。
⇒ **判响应性质必须看原始字节**（至少 `repr(raw[:500])`）；**去标签只适合做正文摘录，不适合定性**。

**派生判据 ③：参数"被回显" ≠ 有 XSS —— 必须投真 payload 看原始字节。**
亲例 `/login/sso?from=X` → `X ,ssoLoginContext is not available.`，看着像反射型 XSS；实测
`<b>`→`&lt;b&gt;`、`">`→`&quot;&gt;`、`'`→`&#039;`、空格→`&nbsp;` ⇒ **输出编码正确，无 XSS**。
⇒ 别用"它把输入回显了"当结论，要投 `<b>` / `"><script>` / `'><img onerror>` 三类真载荷比字节。

---

## 18. ★★ 「写操作 PoC」的两阶段测法：先零写入判「闸可不可绕」

**问题**：很多上传/写文件类 PoC（亲例致远 `fileUpload.do?method=processUpload`）的**第一步就是写文件**。
一旦按 PoC 原样打，**无论成不成，你都已经在生产上投了东西**。而"闸能不能绕"这件事，
**用 GET 就能先判**，根本不需要走到写入。

**做法（把一次潜在写入降级成零副作用的否定）**
1. **阶段 A（零写入）**：只发 **GET**，比对**基线（直连受保护路径）**与**各绕过形态**的响应：
   - 基线 = 直连 → 若得到「需会话」指纹（亲例 450B「被迫下线」）⇒ **端点存在 + 有闸**
   - 绕过形态 → 只要全部落在「**404 / 400 / 规范化掉**」，就说明**请求根本没到 handler**
     ⇒ **闸未破** ⇒ **直接退出，不进入写入阶段**
2. **阶段 B（仅在 A 成立时才做）**：投**惰性内容**的文件 ——
   文件名用能证明"扩展名限制被绕过"的那个扩展名（亲例 `.jsp`），
   但**内容只放纯文本随机标记串**（不含 `<%`、不含任何可执行代码）⇒ 即使被当脚本解析也只是回显文本。
3. **阶段 C**：回读标记串证明「写出且可访问」；同时**先想清楚怎么删**（删不掉就要在报告里写明残留路径）。

★ **亲例结果（致远 `oa.cdcas.com` V8.1SP2，用户已同意执行）**：
阶段 A 11 个形态（PoC 原形态 `../../` + `../` + `%2f` + 反斜杠 + `....//` + `;/../` + `.css/..;/` +
`;x=1` + `/..;/` + 完整路径双层）**全部 404 / 400 / 404/0B**，基线 450B
⇒ **闸未破 ⇒ 阶段 B/C 自动跳过 ⇒ 全程零写入**。结论从"打了一个上传"变成"**未复现，且零副作用**"。

## 19. ★ 路径穿越型过滤器绕过：必须测「变体矩阵」，且**分清 400 / 404 / 403 各是哪一层**

不同「前端 + 容器 + 框架」组合对 `..` 的规范化行为**完全不同**，单测 PoC 原形态会误判"不存在"。

**变体矩阵（亲例全测，11 个）**：`../`（单层）· `../../`（PoC 原形态）· `%2f` 编码斜杠 ·
`..%5c` 反斜杠 · `....//` · `;/../`（分号+穿越）· `.css/..;/` · `;x=1`（矩阵参数）· `/..;/` ·
完整路径双层 · 编码后的完整路径。

**分型（亲例实测）**
| 响应 | 说明 |
|---|---|
| **404 / 0B + `Server: nginx`** | 被**前端**规范化/拒绝（请求没到应用） |
| **404 / 产品自带 404 页** | 到了**应用**，但没匹配上 handler |
| **400 + 应用自己的错误文案** | **应用显式拒绝**（亲例「系统出现错误，请确认访问路径的有效性」） |
| **200 + 产品「需会话」指纹** | 到了 handler 且**闸生效** |
| **200 + 正常业务响应** | ★ 绕过成功 |

★ **别把「PoC 打不通」写成「不存在该漏洞」** —— 亲例口径只写「**公开 PoC 形态未复现**」，
并列出**测了哪些形态**，这样读报告的人能判断是"产品修了"还是"部署形态不同"。
★ **连带发现值得记**：亲例这套（nginx + Tomcat + V8.1SP2）对路径穿越绕过**整体不敏感** ——
早先单测的 `;x=1` / `;Jsessionid=` / `autoinstall.do.css/..;/` 也全 404，两种测法互相印证。

---

## 20. ★★ 改密/写操作类接口的"探测设计"：路由存在性 ≠ 洞成立，且接口往往不能当 oracle

**背景**：`resetPassword`（未授权短信验证码绕过重置密码）这类洞，PoC 一步就是**改掉真实账号的口令**。
但"这东西到底存不存在 / 它要什么请求体"**完全可以在不碰任何真人的前提下问清楚**。

**亲例（致远 OA V8.1SP2，`POST /seeyon/rest/phoneLogin/phoneCode/resetPassword`）**
| 探针 | 响应 | 拿到了什么 |
|---|---|---|
| `GET` 该路径 | 200 / 373B 通用异常页 | 端点存在 |
| `POST` 空 body | **415** | **它要 JSON body** |
| `POST` 畸形 JSON（`{`） | **500** + Jersey `Unexpected end-of-input…` | **确认消费 JSON** |
| `POST {"loginName":"<不存在的账号>","password":"x"}` | 200 / `{"code":3,"message":"非法操作！"}` | **输入校验通过、进了业务判断**；且拿到"不命中"的响应签名 |
| `GET /seeyon/rest/phoneLogin/`（**模块根对照**） | **401 `code 1010`** | ★ **模块根要会话而本接口不要 ⇒ 未授权可达成立** |

**★ 关键结论一：「未授权」要拿"同模块的受保护兄弟路径"当对照** ——
只测目标接口返回 200 说明不了什么（可能是空转）；**同一模块的根/兄弟返回 401「被迫下线」而它 200**，
才证明"闸在别人身上、不在它身上"。

**★ 关键结论二：请求体形状 = 洞的"契约级"证据。** 亲例 body 是 `{loginName, password}` ——
**根本没有验证码字段** ⇒「不校验短信验证码」在**输入契约层面**已经成立，
即便最终没能打出"成功改密"，这条也够写进报告的基础事实。

**★★ 关键结论三（容易踩的坑）：改密接口**不能**当账号存在性 oracle 用**
—— 对**存在的**账号探测一次，**就已经把它的口令改掉了** ⇒ **"判定"与"破坏"是同一个事件**。
所以"试一串管理员名看哪个存在"实质＝**批量改密**，每个命中都是真实人员的凭据被改。
⇒ 想做这种枚举，必须**逐个/逐批拿明确同意**，并且**给每次改出来的口令用高熵随机值 + 事后交给用户**
（把"不可逆"压成"可恢复"）。

**★ 附带纪律：改密类 PoC 落地时，把 PoC 里的弱口令值换掉。**
亲例 PoC 用 `"password":"888888"` —— **命中就等于给超管留了一个可猜口令**（我们自己开的后门）。
⇒ 一律改用**高熵随机值**，并把值写进报告交给用户/校方，让他们登入后改回。

**★ 再附带一条拼写教训（§15 的追加）**：亲例 `resetPassword` 我先前判"404 / 路由不存在"，
其实那次跑的是**拼错前缀**（`/seyeon`）的版本；修正前缀后它 **200**。
⇒ **凡是"404 判定"，都要回头确认那一次跑的是不是正确前缀**；否则会把"前缀写错"记成"端点不存在"。

---

## 21. ★★★ 产品自带的「**免登录白名单**」是未授权面的权威来源（致远 `needless_check_login.xml`）

**比 web.xml 更值钱的一份文件**：致远 A8 把「**哪些路径的哪些方法不需要登录**」写在
`seeyon/WEB-INF/classes/needless_check_login.xml` 里（`<bean><id>/xxx.do</id><methods><method>yyy</method>…`）。
亲例在 `passwa11/seeyon-A8-code` 里拿到真实部署的这份文件 ⇒ **一轮就把未授权面拿到手**，不用猜、不用爆破。

**★★ 它的第一价值是"解释既有观测"**：
| 观测 | 白名单给的解释 |
|---|---|
| `/thirdpartyController.do?method=access` 能匿名渲染页面 | `access` **在白名单里** ⇒ **匿名是设计行为，不是绕过** |
| `/fileUpload.do?method=processUpload` → 450B「被迫下线」 | 白名单**只免检 `showRTE`**，`processUpload` 不在 ⇒ 被闸 |
| **`getAjaxDataServlet` 的 `S`/`M` 是硬闸** | **该 servlet 完全不在白名单** ⇒ **不可达是结构性的** |

**★★ 第二条价值：免检是「路径 + method」**双维**的** ——
⇒ **同一个 `.do` 的不同 `method` 鉴权可能完全不同**。
这条推翻了"这个路径要登录 ⇒ 这个接口都要登录"的直觉：**必须按 method 分别测**。
（亲例：`fileUpload.do` 的 `showRTE` 免检可达/`processUpload` 不可达；`individualManager.do` 的 `resetPassword` 免检。）

**做法**：`search_code` 查 **`needless_check_login`** 或 **`needless_check_login.xml`**；
拿到后逐条探活，分成三堆 —— **可达且活 / 可达但 handler 自检（有响应无数据）/ 本版本 404**。
★ 无参探测时若不传 `method`，很多条目会因"method 为空匹配不到"而仍被拦，**别据此判"白名单失效"**。

## 22. ★★ 判「公开 PoC 是否可用」之前，先审**它自己的成功判据有没有判别力**

**亲例（致远 thirdpartyController 任意用户登录）**：某 Exp 的判断是
```java
if (response.statusCode==200 && response.getHeader("Set-Cookie") != null) { 存在漏洞 }
```
—— 但**我们每次请求都会拿到 `JSESSIONID`** ⇒ **这个判据恒为真，零判别力**。
跟着它跑只会得到假阳性。**实证**：假值 enc 与"真值" enc 返回**同一张匿名页**，且拿到的会话访问
`/seeyon/main.do` 与匿名基线**逐字节相同** ⇒ 未复现。

**做法**：拿到任何 PoC，**先读它的 matcher/判定逻辑**，问一句"这个条件在**不中漏洞**时会成立吗？"
- 若会（如"有 Set-Cookie"、"状态码 200"、"响应非空"）⇒ **判据无判别力，必须自己另设判据**（差分 / 字节比对 / 身份态比对）。
- ★ 更狠的一步：把 **PoC 里的载荷原样打一发**，再问"响应与基线**逐字节**是否相同"。
亲例还顺带解出了 `enc` 的算法（**URL解码 → base64 → 逐字节 -1 凯撒**），
明文只是 `L=message.link.doc.folder.open&M=<数字>&T=<数字>` —— **静态能力串 + token，不含任何用户身份**
⇒ 也从"载荷内容"这一侧确认它造不出"登录成谁"。

---

## 23. ★★ 「免登录面」有**两套机制**：XML 白名单 **+ `@NeedlessCheckLogin` 注解**

`needless_check_login.xml`（见 §21）**不是全部**。致远在代码里还有一个**方法级注解**：

```java
@NeedlessCheckLogin
public ModelAndView upgrade(HttpServletRequest request, HttpServletResponse response) { ... }
```

**亲例（2026-09-26，`oa.cdcas.com` V8.1SP2）**：`EdocUpgradeControllor.upgrade` 在
`passwa11/seeyon-A8-code` 的源码里带 `@NeedlessCheckLogin`，而 `needless_check_login.xml` 里
`/edoc/edocUpgradeControllor.do` 也列了 `upgrade` —— **两处一致**。
但 `MainController` 里 `qrCodeHelp` / `updateLoginSeed` / `index` / `login4Ucpc*` **都带注解**，
**XML 里未必逐条列出**（XML 是给"客户改造/补漏"用的，注解是开发写的）。

**做法**：两条来源**都拿** ——
1. `search_code` 查 **`needless_check_login`** ⇒ 拿 XML 清单
2. 拿到**真实源码仓库**后，`grep -rn "@NeedlessCheckLogin"` ⇒ 拿注解清单
★ **交叉验证**：两边不一致的条目，以**实测**为准（亲例 `/ext/getClientIp.do?method=getClientIp`
在 XML 里但**实测 450B 仍受闸** ⇒ 该路径实际未部署或另有覆盖）。

---

## 24. ★★ 判「某个方法能不能被 URL 直接调」= 看**签名形态**

Java 里"能被 URL 调到的方法"（handler）与"看起来一样危险的内部方法"，**只差签名**：

| 形态 | 能否 URL 直接调 |
|---|---|
| `public ModelAndView xxx(HttpServletRequest, HttpServletResponse)` | ★ **是 handler**（致远/Spring MVC 形态） |
| `public void xxx(HttpServletRequest, HttpServletResponse)` | **是**（少见的 void handler，亲例 `updateLoginSeed`） |
| **`public void xxx(HttpServletRequest, HttpServletResponse, String)`** | ★★ **不是** —— 多一个参数 ⇒ **内部方法**，只能被别的代码调用 |
| `private xxx(...)` / 带业务参 | 不是 |

**亲例（本知识库 §21/§22 同一目标）**：`MainController.loginSystem(request, response, guestLoginName)`
**用 `guestLoginName` 直接构造登录态**（`session.setAttribute(SESSION_CURRENT_USER, currentUser)`）
—— 单看方法体就是**任意用户登录**。但：
1. 它是 **`public void` 三参** ⇒ **不是 handler**，URL 打不到；
2. 它的**唯一调用点**在 `index()` 内，实参是 `guestManager.getDefaultLoginName()`
   ⇒ **服务端配置值，不由请求方控制**。
⇒ **排除**。

★★ **纪律**：见到"看似可利用的方法"，
**先问两句**：① 它是 handler 形态吗？② **把它的调用点全部找出来（`grep 方法名`），看实参能不能被请求控制？**
—— 只看方法体就下结论，会同时犯"高估"（内部方法当入口）和"低估"（漏掉真入口）两种错。

---

## 25. ★★★ 免登录端点里「**升级 / 迁移 / 初始化**」类动作：先读源码的**状态机**再打

这一类端点（`*Upgrade.do`、`upgradeControllor`）**往往自带状态机**，是否真的执行写操作
**取决于服务端当前状态**，与请求参数无关：

**亲例（`EdocUpgradeControllor.upgrade`，`@NeedlessCheckLogin` ⇒ 匿名可达）**
```java
int state = upgradeManager.getUpgradState();
if (state == DOING) "升级中。。。";
else if (state == DONE) "已经完成升级。。。";          // ← 观测落这一支 ⇒ 未执行
else if (state == DONE_ERROR) "升级出错了。。。";
else if (state == NEEDTODO_NO) "无需升级。。。";
else { setUpgradeState(DOING); upgradeManager.upgrade(); ... }   // ★ 只有落这里才真写
```
⇒ **同一发 GET，落在不同状态分支的后果完全不同**（一个纯读、一个真迁移数据）。

**做法与口径**
1. **打之前**：拿到源码（`search_code` 查类名）；**没有源码就先别打**，或**只打一次**并记录响应文案。
   ★ 响应的文案**就是状态机的分支标识** ⇒ 能反推自己落在哪一支（亲例"已经完成升级" = `DONE` ⇒ 未写）。
2. **对照**：把文案与源码里的字符串**逐个对上**（亲例四个文案与四条分支一一对应）。
3. **口径**：若落点无法判定 ⇒ 写「**handler 免登录可达；其是否改变状态无法从响应判定**」，
   **不写"已触发"、也不写"确认只读"**；**不要重打**（重复触发是唯一能把"可能"变成"确实"的动作）。
4. ★ **自己复盘要诚实**：若打的时候**不知道它有写语义**，就照实写"当时按只读探测打的" ——
   这类记录的价值比"结果"高（下一个人能据此调整）。

★ **同类**：`/form/formUpgrade.do?method={toUpgrade,upgrade,viewUpgrade}`（白名单免检三个方法）、
`/autoinstall.do`（白名单里 `method=*` 全免检）—— **升级/安装类端点天然是高危写操作的藏身处**。

---

## 26. ★ 「参数契约矩阵 + sha 坍缩」批量判「这个端点吃哪些参数」

对**一批**免登录端点，用统一套路一次判完（亲例 15 组 × 50 发）：

```
每个端点，先打「无参基线」，再逐个加「猜的参数名=值」，全部 GET、全部落 raw、算 sha
→ 组内 sha 不同 ⇒ 该参数被消费；组内 sha 全同 ⇒ 参数未被消费
```

**亲例产出（一次拿到 12 个"参数不消费"的硬否定 + 3 个"参数被消费"的方向）**
- `edocUpgradeControllor.do?method=download`：**10 个参数变体同一 sha、恒 200/0B** ⇒ 不消费 ⇒ 收口
- `m3/homeSkinController.do?method=getSkinImageUrl`：8 个参数名全不匹配（仍 `NumberFormatException`）
- `/main.do?method=login`、`/personalBind.do?method=retrievePassword`：**sha 随 `loginName` 变** ⇒ 参数被消费 ★
- ★ **必带"对照形态"**：亲例加了 `method=<压根不存在的方法名>` 与 `method=` 空值两发，
  用来区分"**method 本身不被识别**"（亲例 450B「被迫下线」）与"**method 被识别但参数不消费**"（亲例 0B）。
  **没有这个对照，会把"method 名写错"误读成"参数不消费"。**
★ 与 §13（sha 坍缩法）同一招，本条是它的**批量版**；与 §12（参数形态矩阵）同一思路，本条是它的**跨端点版**。

---

## 27. ★★★ 判「参数是否被消费」之前，必须先排除 **session 状态** 这个变量

**亲例（2026-09-26，致远 `personalBind.do?method=retrievePassword`）**

| 场景 | 响应 |
|---|---|
| **全新 session**，首次请求，**带** `loginName=xxx` | **35567B** |
| 同一 session，后续请求，带 `loginName` | **33983B** |
| 同一 session，**不带** `loginName` 的首次 | 35567B |

我第一轮把 `35567 → 33983` 直接读成「**参数被消费**」——**表述不够准**：
差异的**直接变量是 session 状态**（第一次调用把用户名写进 session，之后服务端渲染的是"选择验证方式"页），
而**不是"本次请求带没带参数"**。参数**确实**被消费（写入了 session），但**判据本身选错了**。

**做法**
1. 每换一个参数形态之前，**先把 session 重置**（丢弃 cookie jar / 用全新 session），再打同一发。
2. 或者在同一 session 内**补一发"不带参数"的对照**：若它也变得与"带参数"相同 ⇒ 差异来自 session，不是参数。
3. ★ 尤其注意：**有状态的接口**（找回密码、向导、多步流程）**几乎都有这个问题**。
   顺序敏感 ⇒ **必须记录请求序号**，否则"第 N 发的响应"无法归因。

---

## 28. ★★ 拿到公开 PoC 后，**先把「判据原文」取出来**，再看它自己的探测逻辑有没有判别力

**亲例（致远前台任意用户密码修改）** —— 两边都拿到了原文，价值极高：

**① nuclei 模板（ProjectDiscoveryAI 写）直接写了成功判据**
```yaml
# seeyon-oa-unauth-reset-passwd.yaml
#  Step 3 访问接口，返回 true 则密码被重置为 1qaz@WSX
#  /seeyon/individualManager.do?method=resetPassword&nowpwd=1qaz@WSX
matchers:                       # 但它自己的 matcher 只是"存在性"
  - type: word
    words: ["<title>找回密码</title>"]
  - type: status
    status: [200]
```
⇒ ★★ **模板的 matcher（存在性）与描述里的成功判据（返回 `true`）不是一回事**。
**照着 matcher 打只会得到"这站有这功能"，与"能不能改密"无关。**
本轮就是靠描述里那句 `返回 true` 设的判据，实测拿到 `false` ⇒ 才能干净地说"未复现"。

**② 多仓库同一 PoC，**关键参数取值不一致** ⇒ 必须把取值当变量测**
| 来源 | Step2 的 `origin` |
|---|---|
| nuclei 模板（ProjectDiscoveryAI） | **`system`** |
| 博客与 31 个 PoC 文档 | **`zx`** |
⇒ 取值**不固定**说明"关键点是**传了这个参数**，不是它等于什么"。
**做法**：把两个值 + **不带该参数** 三种都测一遍。亲例三种响应**同一 sha** ⇒ **该变量被排除**，推论更硬。
★ **若只测 PoC 里那一个值，结论只能写"该取值未复现"**，不能写"该机制不可用"。

**③ 口径仍守 §22/§14**：写「**公开 PoC 形态未复现**」，**不写「已修复」**（另一层校验的存在与补丁不可区分）。

---

## 29. 致远 OA（Seeyon）公开漏洞面 → **本目标 V8.1SP2 实测结果**对照表（2026-09-26）

> 用法：遇到致远目标，**先按「免登录白名单」+ 本表逐条对**，能省掉大量猜路径。

### 29.1 公开 PoC 清单（可直接检索的仓库/文件）

| 漏洞 | 检索关键词 | 备注 |
|---|---|---|
| **前台任意用户密码修改**（本次重点） | `sendVerificationCodeToBindNum` / `seeyon-oa-unauth-reset-passwd` | **31 个仓库**有 PoC；**nuclei 模板**在 `onewinner/Lightx`、`damn77789/nuclei-pocs`；代码分析在 `fanygit.github.io` 2024-03-13 |
| **M3 Server 反序列化 RCE** | `seeyon-m3server-mobile_portal-rce` | `mobile_portal/api/pns/message/send/batch/6_1sp1` → `api/systemLog/pns/loadLog/app.log` |
| **XXE（QVD-2023-30027）** | `getAjaxDataServlet` / `xmlValue` | 实例分析在 `myh0st/scripts` |
| **文件上传绕过** | `fileUpload.do` / `safeCheck` | `jemus17/FOCI-Toolkit`、`eeeeeeeeee-code/POC` |
| **白盒审计 + 过滤器清单** | `SeeyonAudit` / `needless_check_login` | `ax1sX/SecurityList`、`passwa11/seeyon-A8-code`、`zhanght86/seeyon_v3x` |

### 29.2 ★ 「前台任意用户密码修改」的确切 PoC 与判据

```
1) GET /seeyon/personalBind.do?method=retrievePassword&loginName=<真实用户名>
     ← 把用户名写入 session（页面 <title>找回密码</title>，即 nuclei 的存在性 matcher）
2) GET /seeyon/personalBind.do?method=sendVerificationCodeToBindNum&type=validate&origin=<zx|system>
     ← 分析称：origin 有值即把 session 的 canModify 置为 true，跳过短信校验
3) GET /seeyon/individualManager.do?method=resetPassword&nowpwd=<新口令>
     ← ★★ 判据：返回 true = 改密成功（PoC 固定口令 1qaz@WSX）
```
★ 三个端点**全在 `needless_check_login.xml` 白名单里**（`/personalBind.do` 免检 6 个方法、`/individualManager.do` 免检 `resetPassword`）
⇒ **免登录是设计，不是绕过**。前提：**必须知道一个真实用户名**。

### 29.3 本目标（V8.1SP2 / build 2023-01-16）实测

| 环节 | 结果 |
|---|---|
| 三端点可达性 | **全部 200、免登录可达 ✓**；`retrievePassword` 命中 nuclei 判据 |
| 步骤 2 | **卡在图形验证码**：响应只有 `{"verifyImageCodeEquals":"false"}` ⇒ **未走到置 `canModify` 的逻辑** |
| `origin` 取值 | `zx` / `system` / **不带** —— 步骤 2 响应**同一 sha** ⇒ **取值不是关键变量** |
| 步骤 3 | **恒 `false`，且与「完全无前置基线」逐字节相同** ⇒ **改密逻辑从未进入** |
| 口径 | 「**载体免登录可达；公开 PoC 三步未复现；零状态改变**」；**不写"已修复"**（图形验证码层与补丁不可区分） |

★ **要证到"改密成功"必须同时满足**：① 一个**真实存在的登录名** ② **通过图形验证码**。
②意味着需要识别 `/seeyon/verifyCodeImage.jpg`；①意味着**会改掉真人的口令（不可逆）** ⇒
**这条从"外部验证"降级为"应由校方用可控测试账号自查"** 的典型情形（见 `recon-methodology.md §25`）。

### 29.4 ★ 几个免登录端点的高危候选（本目标实测）

| 端点（免登录） | 实测 | 性质 |
|---|---|---|
| `edoc/edocUpgradeControllor.do?method=upgrade` | 200 / `alert("已经完成升级。。。")` | ★★ **未授权升级触发器**（源码：非四态时执行 `upgradeManager.upgrade()`） |
| `form/formUpgrade.do?method=viewUpgrade` | 200 / `alert("…权限升级成功!")` | 同上族；**是否变更状态不可判** |
| `autoinstall.do` | 白名单里 `method=*` **全免检** | 安装类，高危写操作藏身处 |
| `uc/rest.do?method=sendsms` | 白名单免检（**未测，涉发短信第三方**） | 短信类，需谨慎 |
| `main.do?method=login4Ucpc3` | 200 / `{"code":"1","LoginOK":"fail","message":"无效的用户名或密码"}` | 免登录**登录校验口**；**四种字段形态同一响应，不泄露账号存在性** |
| `fileUpload.do?method=showRTE` / `fileDownload.do?method=showRTE` | 200 / `NumberFormatException` | 参数名 = `fileId`；**连其自身公开的 fileId 都 404/0B ⇒ 未取得文件** |

---

## §30 ★★ 扫描器「未授权 / 协议指纹」类判定必须带**阳性对照**

> **通用规则**。亲例（uWSGI / XXL-JOB / H2 三例）见任务归档 `工作区/内网_SRC挖洞/*_误报复核_*/结论.md`。

### 30.1 ★★ 根因通用式：把**否定信号（无响应 / 无差异）当成了肯定信号**

扫描器「协议 / 产品识别」类误报的**统一根因**：

```
端口开放 → 发探测包 → 得到「空响应 / 无差异 / 通用错误」
        → 判成「产品在」 → 再跑该产品的利用分支 → 同样拿到否定信号
        → 记成「漏洞可用」
```

★ **缺的那一步就是"阳性对照"**：没有先验证「真产品收到这种包**必须**回什么」，
于是**任何给不出差异响应的开放端口都会被记成命中** —— 命中率 ≈ 端口开放率。

★★ **通用纪律（可套到所有协议/产品识别误报）**：
**一个没有判别力的判据，等价于没有判据。** 用它之前先问：
**「如果目标上没有这个服务，它会回什么？和命中的响应能区分开吗？」** 答不上来就不能采信。

★ 三条通用反制（**必须同时满足**才算命中）：
1. **有无对照组**：至少一个「该产品必然给出的正响应形状」。
2. **有无差异**：命中形态与「无该产品」形态**可区分**。
3. **是否特异**：该响应是否**只有这个产品**才会给（否则可能是通用兜底/网关）。

### 30.2 ★ 二进制协议探测的通用判据：**"必须回报错误" vs "静默关闭"**

判某个二进制协议服务是否存在时，**关键不是"发对包有响应"，而是"发错包也必须回错"**：

| 情形 | 含义 |
|---|---|
| 发**超限 / 畸形**包 → 得到**协议专属错误串** | ★ **有该协议的解析器**（这是判据来源） |
| 发**超限 / 畸形**包 → **静默关闭 / 0 字节** | ★ **该端口没有该协议解析器** |
| 发**纯文本 HTTP** → 回**正常 HTTP 响应** | 是 HTTP 服务（除非该协议显式支持 `--http` 模式） |

**通用手法**：拿「协议规定的**必有错误分支**」当探针 —— 协议实现里「输入非法时必须回错误」
是**固定行为**，可当**阳性对照**。**静默关闭 = 否定证据，绝不是肯定证据。**
★ 三条独立判据（超限包 / 合法包 / 文本包）**同向**，结论才站得住。

★ 诱因提示：目标端口若是**业务自选端口**（非协议默认端口），误报概率显著放大 ⇒ 优先怀疑。

### 30.3 ★ 单入口 token 网关的识别模板（★ 这类形态极常见）

**形态特征**：一个**所有路径共用同一入口**的网关，先校验 token，未过则回固定拒绝文案。

| 观察 | 说明 |
|---|---|
| 任意方法 / 任意路径 → **同一串固定响应** | ★ **不看路径** ⇒ 单入口，不是路由型应用 |
| 仅某一种 method → 换一句固定文案（如「token 错误」） | 该 method 走到**鉴权分支** |
| `HEAD` → 仅响应头、无 body | 语义正确（真 HTTP 服务） |
| 空连接（连上不发）→ 0 字节 | 静默等待 |
| `Content-Type: text/html;charset=UTF-8` + JSON body | **Java `@RestController` 未设 `produces` 的默认头** ⇒ 别误判成 HTML 页面 |

★★ **口径**：「要求 token 且拒绝匿名 ⇒ **鉴权闸在工作，这不是漏洞**」。
要打是「**token 校验是否可绕**」，那是**独立战线，禁跨题外推**。
★ **这类网关是大量"协议/产品识别"误报的共同真身** —— 遇到"任意路径同一响应"就先往这上面想。

### 30.4 ★ 取证链路通用踩坑（影响同类任务）

- **扫描器结果可能不保留原始报文**：`Detail` 字段为空 ⇒ **无法直接审计其判据，必须自行复现**。
  （`Detail`/`poc_req`/`poc_resp` 有值时**优先读它**，那是一手证据。）
- 扫描器的**判定逻辑通常不在本地文件**（在二进制内）⇒ 机制只能**推断**，写结论时**要标明是推断**。
- **扫描器自己标注的「高误报风险」是真信号** ⇒ 见到该标记的条目默认按「必须先复核」处理，不进报告。
- ★ **资产核对**：扫描器报的 IP/端口与实际开放的**可能不一致**，落报告前**必须回验目标可达性**。


---

## §30.5 ★★ 「状态码 200」是最弱的判据：catch-all 网关能让任意路径都回 200

**通用现象**：扫描器把「特征端点返回 200」直接当成「产品存在」。但一个 **catch-all 网关 / SPA 兜底路由**
会让**任意路径**都回 200，此时该判据的命中率 = 100%，**等于没有判据**。

**★ 核心反制：路径无关性对照（path-invariance control）**
拿 **≥4 个语义无关的路径**各打一发（如 `特征端点` / `/` / `/api` / 一个不存在的路径），
比较响应的**原始字节**：
- **逐字节相同 ⇒ catch-all，不是特定产品** ⇒ 判据无效，结论只能是「该形态未到达应用」。
- 有差异 ⇒ 再进入下一步，比较差异点是否与产品指纹吻合。

★ **必带"不存在的方法名/路径"对照组**：没有这个对照，「参数/路径不消费」会被误读成作者以为的结论。

**★★ 响应体形状 > 状态码**：判某个产品是否存在，先取该产品特征端点的**真实响应形状**
（纯文本？JSON？固定长度？带版本串？）。
- 反例：某产品的 `/beat`/`/health` 类端点真实返回**纯文本时间戳/纯文本状态词**；
  若实测回的是**固定 JSON**、且换个路径回同一串 ⇒ **不是该产品**。
- **形状不符即排除**，不必再纠结状态码。

**可复用判据（三条一起用）**：
1. **路径无关性对照**：≥4 个语义无关路径，响应逐字节相同 ⇒ catch-all，非特定产品。
2. **响应体形状对照**：与产品特征端点的**已知真实形状**比对（类型 / 长度 / 关键串）。
3. **端点特异性**：真产品的指纹端点换成任意路径后**必然改变行为**；不变则判据无效。

★ 同构纪律（见 §30.1）：**「200」本身没有判别力**——catch-all 网关命中率 100%。
把「状态码 200」当判据，等价于把「端口开放」当判据。

---

## §30.6 ★★ 「未授权访问」类页面暴露：拦截页**覆盖到静态资源**才说明是全局闸

**通用现象**：某管理控制台（H2 Console、Druid 监控、Actuator、XXL-JOB 后台等）的入口页可匿名访问，
扫描器即报「未授权访问」。但**页面可达 ≠ 功能可用**——服务端可能在**入口做了全局前置检查**。

**★ 判据：对子路径做覆盖矩阵，看拦截是否延伸到静态资源。**
逐个请求该控制台下的**功能路径 + 静态资源路径**（`.jsp`/`.do`/`login` + `stylesheet.css`/`.js`/`.ico`）：

| 观察结果 | 含义 |
|---|---|
| 所有子路径（**含静态 `.css`/`.js`**）返回**同一张拦截页** | **全局前置闸**——服务端在入口统一拒绝 ⇒ 功能不可用 |
| 拦截页只覆盖功能路径，**静态资源返回真实 CSS/JS**（`Content-Type: text/css`） | 拦截是**逐路由**的 ⇒ 需逐个判断是否有漏网路由 |
| 功能路径返回**真实表单**（非拦截页） | **闸没生效** ⇒ 进入可利用性验证 |

★ **静态资源是否被拦，是区分「全局闸」与「单页面缺鉴权」的关键**：
若只是某个 JSP 恰好没鉴权，`stylesheet.css` 必然返回真 CSS；被同一张拦截页覆盖 ⇒ 是全局闸。

**★★ 定级口径**：
- 命中拦截页（如「远程连接已禁用」类文案）⇒ 属**配置缓解**，
  **不构成「未授权 → 功能 → RCE」链**；最多算**信息级**（暴露了产品/框架指纹）。
- **反例形态（必须对照）**：闸关闭时该页面应返回**真实登录表单**、静态资源返回真 CSS、
  登录接口可提交并换 session —— 那才是可提交的形态。**未见过反例形态，不得写高危。**

**★ 只读纪律**：验证时**只发 GET**；若要探测登录接口是否受理，
body 用**非凭据占位**（空用户名/空驱动/空 token），**绝不投真口令或真实凭据**。



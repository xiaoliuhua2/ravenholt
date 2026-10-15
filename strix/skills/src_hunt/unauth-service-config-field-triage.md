---
name: "unauth-service-config-field-triage"
description: "未授权服务的「配置字段级差分」— 从类型错误反推服务端调用"
---

# 未授权服务的「配置字段级差分」— 从类型错误反推服务端调用

> 适用：目标是一个「无账号、无会话、纯功能型」的服务接口（渲染/转换/导出/截图/水印类最常见），
> 前端有个 SDK 在拼 config，而你不知道服务端怎么消费这些字段。
> 亲例：`pdf.dotfashion.cn/print`（SHEIN，未授权 HTML→PDF），靠这套流程挖出未授权任意文件写入。
> 来源轮次：2026-09-17 第 4 轮。

## 0. 为什么值得做

这类服务通常**只暴露一个入口**（`POST /print` 之类），字段全塞在一个 JSON 里当「配置」。
开发者一般只想着「某个选项有没有生效」，不会对每个字段做类型/取值校验 —— 于是同一份 payload 里
往往同时封着**文件写入路径、代理地址、输出目录、模板路径**这些高危开关。

## 1. 第一步：从前端 SDK 反推 config schema（零网络）

优先去**已落地的前端包**里找调用方（本项目的 `js/<host>/`、小程序解包、APK 里的 Dart/JS bundle）。

**★ 最大的坑：`__rest` 造成的「白名单假象」**

前端常见写法（Babel 编译产物）：

```js
var rest = __rest(config, ["landscape","format","content","inject","echoPrint"]);  // 取出"其余"键
return JSON.stringify(__assign({
  landscape: !!landscape, format, content: _content, inject, echoPrint: !!echoPrint
}, rest));   // ← rest 又被合并回去了
```

看见一长串 PropTypes / 固定字段列表时**不要**当成白名单 —— 只要出现了 `__assign(白名单对象, rest)` / `...rest`，
**所有未列出的键都会原样透传到服务端**。亲例：`watermark / proxy / download / path / autoClose / viewportWidth`
全都是靠这一点才能传到服务端的。

**同时把注释当文档读**：中文注释常直接写明语义（`// 发送到后台进行注入的js和css`、`// 当为true的时候...`），
有时还会泄漏 dev/test/sit/prod 四套环境域名（→ 直接变成下一批测试目标）。

## 2. 第二步：类型污染 oracle（零副作用的「服务端在用它」判定）

逐个字段递**错类型的值**，看响应：

| 传 | 若响应出现 | 结论 |
|---|---|---|
| `true` | `The "path" argument must be of type string. Received type boolean (true)` | 被交给了 Node `fs`/`path`/`child_process` 的 path 形参 |
| `12345` | 同上（`Received type number (12345)`） | 同上，且确认**没有** `typeof` 之类的前置校验 |
| `{}` / `[]` / `"a".repeat(5000)` | 其他内建报错 | 顺带暴露函数名/参数名 |

**判据原理**：`ERR_INVALID_ARG_TYPE`（`The "path" argument must be of type string`）只在 Node 内建
`fs.*` / `path.*` / `child_process.*` 的参数校验阶段抛出，**且是同步抛出的** —— 所以它能穿过
外层 try/catch 被回显出来。这比"猜字段语义"可靠得多，而且**零副作用**（类型错误不会真的写文件）。
亲例：`download: true` → 404 + 该错误 ⇒ 一眼定性「用户可控路径进了 fs」。

## 3. 第三步：用同步/异步错误的差异定 API 形态

同一个参数：

- **类型错误**（同步）→ **可见**，被回显；
- **路径错误** `ENOENT` / `EISDIR` / `EACCES`（异步）→ **被吞**（fire-and-forget `fs.writeFile(p, buf, noop)` 或未 await 的 promise），响应照常 200。

**★ 由此得出的反直觉结论**：
**「传目录进去没报错」≠「这个参数没被使用」**，只是错误死在 callback 里了。
判定「参数有没有被消费」要用**类型污染**，不要用非法路径。

另外：**响应格式变化**也是强信号（亲例：同一字段传 boolean 时 404+错误文本，传 string 时 200+正常 PDF）。

### ★★ 纪律：类型错误只证明「路径进了 fs」，**不证明「写得进去」**

`ERR_INVALID_ARG_TYPE` 出现在响应里，**只能得出一个结论**：这个用户可控字符串被交给了文件写入调用。
它**推不出**「文件真的被写出来了」，更推不出「写入内容可控」。

把这条升格为「任意文件写入 / 高危」之前，**必须先补上「写入落地」的证据**；补不上就只叫
**「文件路径注入（疑似任意文件写入：路径可控已证、落地未证）」**，定级压到中危。

**必须避免的自欺**：「反正写进去我也读不回来，但能写就行」——不对。写入类漏洞的危害确实是
**覆盖/破坏**而非读取，所以「攻击者读不回来」本身不致命；**致命的是「连写进去都没证」** ——
证据链断在半路，评审一问就塌。（亲例：SHEIN `pdf.dotfashion.cn` 的 `config.download`，
最初报成高危「任意文件写入」，被用户一句「写入又读不了」问倒，降为中危。）

**补证的三条路（按性价比排序）**：
1. **白盒看分支**：直接读那段实现，一秒定论（最优）；
2. **找「服务端会读回的文件」**：模板、配置、缓存 —— 若有，覆盖它再看响应变化；
   真不存在就别硬凑（亲例：目标无静态目录 + 内部代理只读对象存储，此路不通）；
3. **覆盖一个已知可观测文件**（如 `GET /` 返回的静态 PDF、`?echoPrint=1` 的模板）——
   这是唯一能远程定论的方法，但它**修改了生产文件**，**必须拿到明确授权才做**。

**降级不是失败**：一个如实标注「落地未证」的中危，远比一个撑不住的高危值钱。

## 4. 第四步：procfs 双面安全 oracle —— 区分「读」还是「写」

路径类参数必须回答：服务端拿这个路径是**读**还是**写**？直接拿 `/etc/hostname` 试是**不行的**（万一它是"写"，就覆盖了系统文件）。

**用 procfs 当探针，两种语义都安全**：

| 探测值 | 若服务端是「读」 | 若服务端是「写」 |
|---|---|---|
| `/proc/self/cmdline` | 读出进程命令行（可能直接看到 `--no-sandbox`！） | procfs 只读，内核拒绝 → **零副作用** |
| `/proc/self/status` | 读出 Uid/Gid/Seccomp 等 | 同上 |
| `/proc/self/environ` | 环境变量（可能含云密钥） | 同上 |

**判读**：把返回内容用「带内文本 oracle」读出来（渲染类服务看渲染结果、导出类服务看导出文件）。
若能读出目标文件内容 ⇒ **任意文件读取**（直接高危）；若返回的仍是自己的输入内容 ⇒ 非读取，按写处理。

亲例：`download: "/proc/self/cmdline"` 的返回 PDF 里仍是我们自己的 HTML 文本 ⇒ 排除读语义。

## 5. 第五步：同一个参数换传法再测一遍

**query string 和 JSON body 常常是两套代码路径，语义可能不同**。亲例（同一个 `download`）：

- FormData 的 `config.download` = **文件路径**（走 fs，boolean 报类型错误）
- `?echoPrint=1&download=...` = **布尔开关**（值被忽略：传 `true`/随机串/`/proc/self/cmdline` 四个值返回**同一个固定文件**）

**判定「值是否参与拼接」的方法**：传 2~4 个差异极大的值，若响应**字节级一致** ⇒ 值不参与，只是开关；
若响应随值变化 ⇒ 值被使用了，继续按 §4 分读/写。

## 6. 卡住的时候：诚实地停下，别越界

写入内容若受限（亲例：只能是 Chromium 生成的 PDF，头固定 `%PDF-1.4`、文本流 FlateDecode 压缩），
就**不能**直接升级为 RCE（写不出有效 shell / cron 行 / `authorized_keys`）。

想「证明写入真的落地」时，常见做法有：写进 `/proc/self/cwd/`、猜静态目录后用 HTTP 取回 ——
亲例两者都失败（服务无静态目录、无回读通道）。此时**禁止**为了让证据变漂亮去**覆盖生产环境的已有文件**
（那是篡改，越过 SRC 边界）。正确做法是：把「路径完全可控 + 确实调用了写入 API」作为结论，
把「内容/落地」标注为**强推断**，并写清还差什么才能坐实。

## 7. 顺带该查的两件事

- **调试端口**：`/json/version`、`/json/list`（CDP）。若某服务把 Chromium 的调试端口反代出来，
  **直接就是免利用的浏览器控制**，比任何内存破坏都省事。亲例：404，排除。
- **健康/版本/文档端点**：`/health`、`/version`、`/metrics`、`/swagger`、`/openapi.json`、`/robots.txt`。
  注意区分「服务自己的 404/200」和「WAF 拦截页」（本项目：2662 字节 / `GSRM Security` / `STATUS:403`）。

## 8. 进阶：前端里的「自研代理路径」= 内部端点金矿

服务端往往给业务前端提供一个**自研代理**，用来把私有对象存储/内部接口暴露给浏览器。
这类路径**写在前端 HTML/JS 里**，而且通常**不带签名**（因为前端直接 `iframe.src` / `fetch` 用）。

**怎么找**：把服务端返回的 HTML 外壳页、以及已落地的前端 bundle，扫一遍 `src=` / `href=` / `fetch(` / `location=`，
凡是以 `/` 开头、长得像内部命名空间的（`/xxx-proxy/`、`/gw/`、`/api-inner/`）都挑出来。
亲例：`pdf.dotfashion.cn` 的 `?echoPrint=1` 外壳页里写死
`iframe.src = '/pdf-proxy/pdf2/<host>/<日期>/<毫秒ts>-<32hex>.oss.pdf'` —— 一个无签名的 OSS 代理。

**拿到代理后按顺序问四个问题**：

1. **它放行什么前缀？** 逐个前缀试（`/proxy/<prefixA>/`、`<prefixB>/`），看返回 200 / 401 / 403 / 404 的区别。
2. **前缀白名单能不能绕过？** 按这个顺序试：
   `//` 双斜杠 → `..;/` → `%2e%2e%2f` → `..%2f` → 大小写 → `./`
   亲例：`/pdf-proxy//html/...` **一次即中**（`html/` 本该 401，双斜杠让它变 200）——
   原因是**规范化发生在前缀检查之后**。
3. **能不能列举？** `?list-type=2`、`?prefix=`、`?max-keys=`、目录结尾 `/`。
   亲例：全部 404 ⇒ 只做单对象 `GetObject` ⇒ 影响半径取决于「key 是否可预测」。
4. **读的是谁的数据？** 用**自己请求产生的 key** 做证明，不碰他人对象。
5. **★★ 返回的 `Content-Type` 是什么？** —— 这一步最容易跳过，但**它决定危害等级**：
   若目标把「攻击者可控的内容」以 **`text/html`** 返回 ⇒ **XSS**（在目标域下执行攻击者脚本），
   若是 `application/octet-stream` / `application/pdf` ⇒ 只是"读文件"，**量级完全不同**。
   **亲例（SHEIN pdf 服务，2026-09-18）**：`/pdf-proxy//html/<key>` 返回
   **200 + `Content-Type: text/html` + 攻击者提交的 HTML 原文** ⇒ 构成**存储型 XSS**
   （完整链：未授权提交含 `<script>` 的 HTML → 服务端持久化到对象存储 → 错误信息回显自己的 key
   → `//` 绕过 ACL 读回 → 把 URL 交给受害者）。
   **教训**：我第一次拿到这个响应时只记了「200 + 647 字节 + 绕过成功」，**漏看了 `text/html`**，XSS 晚一天才被发现。
   **规则：读回可控内容后，第一件事是看它的 `Content-Type`。**

## 9. 对象存储 key 的熵：改请求头，看 key 变不变

key 里常混入请求派生字段，逐个改头观察：

| 改动 | 若 key 中某段随之改变 | 含义 |
|---|---|---|
| `Origin` / `Referer` | `<host>` 段变了 | **键位注入**：攻击者可控制 key 前缀（亲例：`Origin: https://evil-test.example` → `pdf2/evil-test.example/…`） |
| 无任何 Origin | 出现默认值（亲例 `pdf2/unkown/…`，还带开发者拼写错误） | 说明该段无校验地回落到默认值 |
| `X-Forwarded-For` / `UA` | 不变 | 与 key 无关 |

**再统计 key 中「看起来随机」的那段到底随不随机**：连续取 8~10 次，跨足够长的时间窗。
亲例：32hex 段在 SOFTWARE 模式下**跨 1 小时恒定**（`10c963…`），只在另一种模式下才变化
⇒ **它不是每请求随机**，叠加「host 可控」后，key 的未知部分只剩毫秒时间戳。

**判断影响时要同时看三条**：① 能否列举（不能则必须已知完整 key）；② 未知段有多大熵；
③ 能否用**非自己产生**的对象做最小差分证明。三条缺一，定级就要压住（亲例压到中危），
也**不要为了凑证据去大规模枚举他人对象** —— 那是拖数据，越界。

## 10. 破坏性验证怎么做得「有结论」：崩溃粒度 = 进程模型的照妖镜

当「沙箱是否开启」无法从 JS 观测时（这是常态），**别硬猜启动参数**，转而测**崩溃的影响半径**：

- 让渲染/解析进程吃满内存（受控分级：如 512MB → 1.5GB → 3GB），逐级观察。
- 看**主服务是否受影响**：渲染进程 OOM 崩溃、而 `/health` 与业务接口照常 ⇒ **独立进程**（排除 `--single-process`）；
  反之主服务一起挂 ⇒ 共享进程。
- 亲例：3GB 时返回 `[page-crash] Page crashed!` + `Navigation timeout of 30000 ms exceeded`（耗时 30.5s），
  但崩溃后 `/health` 立刻 200、`/print` 0.93s 正常 ⇒ 隔离良好，同时暴露服务端有 **30s 超时保护**。

**两个必须遵守的纪律**：
1. **HTTP 200 不代表分配成功** —— 一定要用**文本 oracle**（把渲染结果读回来）确认页面里到底是
   `ALLOC_OK` 还是 `ALLOC_FAIL`，否则整个实验毫无意义；
2. **分级 + 可中止**：每级之后必须探活，一旦服务出现不可用立即停止升级，别把生产打穿。

**并且要诚实**：独立渲染进程 **≠** 沙箱开启（`--no-sandbox` 同样是独立进程，只是缺 OS 级隔离）。
测不出沙箱状态就写「测不出」，不要用行业惯例（「容器化 Puppeteer 一般都加 `--no-sandbox`」）冒充结论。

## 11. 从 bundle 的「请求封装函数」反推真实 API 前缀

SPA 的 API 基址/前缀常常是**运行时注入**的（`apiPrefix: ""`、`window.__CONFIG__`），在硬编码字符串里搜不到。
这时**不要**直接拿接口路径去猜，而是去找**请求封装函数里 URL 的最终拼接那一行**。

**在 bundle 里搜这些锚点**：`fetch:` / `axios.create` / `request(` / `baseURL` / `prefix` / `apiPre`，
定位到形如：

```js
x = `${E || "/gmpj"}${x}`;     // apiPre 默认 "/gmpj"，调用方可覆盖
x = h ? h + x : x;             // prefix 可换成绝对域名
B.credentials = "include";     // 鉴权走 Cookie
```

**⇒ 真实 API = `<prefix><apiPre || 默认值><path>`。**

### ★ 为什么必须这么做（亲例踩坑，2026-09-18 gmp-sit01）

不知道前缀时直接打 `/goods/goods/list`，会被**静态托管层**接住：

| 现象 | 真相 |
|---|---|
| `405 {"msg":"仅支持使用 GET 方法访问"}` | **静态托管层只放行 GET**，不是接口的方法限制 |
| `404 {"msg":"获取产物 xxx/版本号/路径 Etag 失败: NotFound"}` | 目标域把未知路径**当成前端产物去对象存储取**了 |

**这两类响应极易被误判成「接口不存在」而放弃。** 加上正确前缀（本例 `/gmpj`）后立刻拿到业务网关的真实响应
（`302 {"code":"100004","msg":"请先登录！"}`）——**这时才真正开始测鉴权**（本例结论：鉴权正常，无未授权）。

**顺带收益**：静态托管层的 404 报文常泄漏**内部产物路径与集群命名**
（亲例 `gmpFront-cnsouth-sit-ackAliyunSitSit/14512916/...` ⇒ 暴露 ACK K8s 集群名），可顺手记成信息泄漏点。

### 配套检查：前端首页的内联脚本

抓首页 HTML 时别只看 `<script src>`，**内联脚本经常直接泄漏 CI/CD 元数据**：
`window.shein_env_config['CI_COMMIT_SHA']`、`CI_COMMIT_REF_NAME`、`X-Build-Time`、`__LEGO__VERSION__`。
（本项目已在 `scm.sheincorp.cn` 与 `gmp-sit01` 两处命中同类泄漏 —— 值得作为固定检查项。）

## 12. ★ 渲染 / SSR 类服务：先做「运行时上下文自检」，再谈危害

当目标是 **服务端渲染 / HTML→PDF / 截图 / 无头浏览器** 类服务，且你能让它在服务端执行脚本时，
**不要直接写「服务端代码执行」** —— 先用一段 10 行自检脚本把运行时能力边界问清楚。
**同样一个"能执行 JS"的现象，落在 Node 上下文、浏览器渲染进程、或禁用了 WASM 的渲染进程里，危害差一个数量级。**

**自检骨架**（塞进被渲染的 HTML，用目标自己的文本/图片 oracle 读回）：

```js
var o=[];
o.push('window:'+typeof window);            // 浏览器特征
o.push('document:'+typeof document);
o.push('process:'+typeof process);          // Node 特征 ← 关键
o.push('require:'+typeof require);          // Node 特征 ← 关键
o.push('module:'+typeof module);
o.push('global:'+typeof global);
o.push('child_process:'+typeof child_process);
o.push('WebAssembly:'+typeof WebAssembly);  // ← 能否执行任意原生"计算"
o.push('SharedArrayBuffer:'+typeof SharedArrayBuffer); // 内存布局可控性
o.push('fetch:'+typeof fetch);
o.push('origin:'+location.origin);
document.body.innerHTML='<pre>'+o.join('\n')+'</pre>';
```

**判读表**：

| 观测 | 结论 | 危害量级 |
|---|---|---|
| `window/document` 有、`process/require` 无 | **浏览器渲染进程**（非 Node） | **中**：不能执行命令，能力受浏览器沙箱限制 |
| `process/require/module` **有** | **Node 上下文** | **高/严重**：可直接 `require('child_process').exec()` |
| `WebAssembly` `undefined` | 原生计算入口被堵 | **降低** RCE 概率（**但不消除** —— V8 JIT 类漏洞不依赖 WASM） |
| `origin` 是**随机伪造域** | 服务端做了 origin 隔离 | 说明开发者有安全意识，通常伴随其它加固（如禁 WASM） |

**亲例（SHEIN `pdf.dotfashion.cn`，2026-09-18）**：自检得 `process/require/module/global` 全 `undefined`、
`WebAssembly` 被禁、`origin` 为 `https://www.taobao-<随机数>.com` ⇒ 结论从「服务端代码执行（高危）」
收窄为「**服务端 JavaScript 执行（中危）**」，**避免了一次会被打回的高报**。

**规则：能执行 JS ≠ 能执行命令。先把上下文问清楚，再定级。**

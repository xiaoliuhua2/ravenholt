---
name: "rendering-service-rce-triage"
description: "渲染服务 RCE 判定：HTML→PDF / 无头浏览器 / SSR 服务"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# 渲染服务 RCE 判定：HTML→PDF / 无头浏览器 / SSR 服务

> 适用：`pdf.*`、`html2pdf`、导出服务、报表渲染、截图服务、SSR 渲染等「服务端跑浏览器」的目标。
> 来源：2026-09-18 SHEIN `pdf.dotfashion.cn` 实证（未授权 Chromium 渲染服务）。
> 本模块只解决一件事：**把「能不能 RCE」从定性讨论变成逐条实测 + 公开利用链比对。**
> 定级仍只认 `load_skill("src_hunt/03-vuln-report-format")`，本模块不定级。

---

## §1 核心认知：先分清「执行 JS」和「执行系统命令」

**「服务端代码执行」是个被滥用的说法。** 同一个"能执行代码"的服务，危害可以差一个数量级：

| 上下文 | 判定方法 | 危害 |
|---|---|---|
| **Node 上下文**（Puppeteer 的 `page.evaluate` 传参、模板引擎、`vm.runInThisContext`） | `typeof process/require/module/global/Buffer` ≠ undefined | ★ **直接 RCE** —— 不用绕沙箱，`require('child_process').execSync()` 就完了 |
| **浏览器渲染进程** | `window/document/navigator` 是 object，`process` 全 undefined | 只能 JS —— 要 RCE **必须再有一个引擎内存破坏漏洞** |
| **同上但 `WebAssembly` 可用** | `typeof WebAssembly` | 公开 PoC 大多能落地（见 §3） |
| **同上且 `WebAssembly` 被禁** | `typeof WebAssembly === "undefined"` | ★ **最成熟的公开 PoC 全部失效**（见 §3） |

**⇒ 报告里写「服务端代码执行」之前，必须先跑一次上下文自检。** 10 行 JS 就能把猜测变成事实。

---

## §2 六步判定（按性价比排序，能走到哪步算哪步）

```
① 上下文类型        typeof process/require/module/global/Buffer
② WebAssembly       typeof WebAssembly          ← 决定公开 PoC 能否落地
③ SharedArrayBuffer 真能 new 成功吗（typeof 是 function ≠ 能构造）
④ 精确 build 号     ⚠️ UA 可能被服务端改写 → 改看 PDF 元数据 /Skia/PDF mXX
⑤ file:// 与出网    决定 the-map §9 路径 1/3 是否关闭
⑥ localhost CDP     127.0.0.1:9222 / :9223 是否可达  ← 有的话是最直接的控制面
```

### 1) 上下文类型 —— 最优先，判错后面全白干

```js
typeof process + '/' + typeof require + '/' + typeof module + '/' + typeof global + '/' + typeof Buffer
```
- 有 `process` ⇒ **Node 级**，直接找 `child_process` / 文件读写，**不用碰浏览器漏洞**。
- 只有 `window/document` ⇒ 渲染进程，继续往下判。

### 2) `WebAssembly` —— ★ 决定「公开 PoC 能不能直接用」

**这是本轮最关键的一步。** 现代 V8 利用链的经典收尾是：
> OOB → 相对读写 → 破坏 TypedArray 得到绝对读写 → **覆盖 RWX 区域的 WebAssembly 函数体写入 shellcode** → 调用该 WASM 函数

**没有 WASM 就没有这块 RWX 页，收尾环节直接断。**
亲例：`xmzyshypnc/CVE-2021-30551`（版本覆盖 87）的 exp.html 就依赖 WASM ⇒ 本目标 `WebAssembly === undefined`，**跑不通**。

⚠️ **注意区分原因**：
- **CSP 导致的**：`script-src` 无 `'unsafe-eval'` 会阻止 WASM **编译**，但 `WebAssembly` 对象**仍然存在** ⇒ 可以试 `typeof eval` 对照。
- **显式禁用**：`--js-flags=--no-expose-wasm` / `--disable-features=WebAssembly` ⇒ `WebAssembly === undefined`。
  亲例：本目标 `eval` 正常但 `WebAssembly === undefined` ⇒ **是显式禁用，属开发者加固**。

### 3) `SharedArrayBuffer` 必须「真构造」

```js
try { var sb = new SharedArrayBuffer(1024); var sv = new Uint8Array(sb); sv[0]=42;
      return 'OK rw=' + sv[0]; } catch(e){ return 'FAIL ' + e.name; }
```
`typeof SharedArrayBuffer === 'function'` **不代表能 `new`**（受跨源隔离策略影响）。
它能构造 ⇒ addrof/fakeobj 布局 + 跨线程 race 原语可用。
（本目标实测 `OK byteLength=1024 rw=42`）

### 4) 精确 build 号 —— ⚠️ UA 可能被改写

**先看 `navigator.userAgent`，但别信它。** 亲例：SHEIN pdf 服务的
`navigator.userAgent === "IE"`（**字面量两个字符**），`appVersion` 同样被改写 —— 说明服务**主动伪造了 UA**。

**UA 不可信时的替代品**：
- **PDF 元数据 `/Producer (Skia/PDF m87)`** ⇒ 直接给出 **Chromium 分支**（mNN = Chromium NN），最可靠；
- 行为特征差分：`navigator.userAgentData`（Chrome 90+）、`Array.prototype.at`（92+）、`Object.hasOwn`（93+）、
  `structuredClone`（98+）、`CSS.supports(':has()')`（105+）—— 逐个探测能**卡出一个版本区间**；
- `navigator.vendor` / `product` 仍是 `Google Inc.` / `Gecko`（未被改写）。

### 5) `file://` 与出网

- `file://` 子资源/同步 XHR → 被 **Chromium 浏览器级策略**拦：
  `Not allowed to load local resource`。
  ★ **这是浏览器策略，与 OS 沙箱是否开启无关** ⇒ **即使 `--no-sandbox` 也读不到文件**。
  ⇒ the-map §9 路径 1（`--no-sandbox` + file 读）**关闭**。
- 出网：用 OOB DNS 测（**务必先做正对照**：本机 `nslookup`/`curl` 打自己的 OOB 域，
  确认通道可用，否则「零命中」不可信）。
- ⇒ 两者都禁 ⇒ the-map §9 路径 3（SSRF 打内网）也**关闭**。

### 6) localhost CDP 端口 —— 有就是最直接的控制面

```js
fetch('http://127.0.0.1:9222/json/version', {mode:'no-cors'})  // resolve ⇒ 端口开
```
Chrome 的 DevTools HTTP/WS 端点默认绑 `127.0.0.1`。若渲染进程能到达它，理论上是**免漏洞的浏览器控制面**。
⚠️ 但仍有两道坎：① DevTools 的 **WS 会校验 `Origin`**（网页发起的 WS 一定带 Origin ⇒ 常被拒；
Chrome 111 起更引入 `--remote-allow-origins`）；② `Host` 头校验（防 DNS rebinding，从 127.0.0.1 发起则天然通过）。
**先测可达性**（不可达就彻底排除）；可达再评估 WS 能否过 Origin 校验。
亲例：本目标 `:9222` / `:9223` 均 `UNREACHABLE TypeError` ⇒ **排除**。

---

## §3 GitHub 公开利用链适用性速查

| 资源 | 覆盖版本 | 对本类目标的适用性 |
|---|---|---|
| `xmzyshypnc/CVE-2021-30551` | < Chrome 91.0.4472.101 | ⚠️ 有完整 exp，**但收尾依赖 WASM RWX** ⇒ 目标禁 WASM 则跑不通 |
| **CVE-2021-21220**（V8 JIT XOR typer） | **< Chrome 89.0.4389.128** | ✅ 公开 PoC 走 **TypedArray/ArrayBuffer 越界，不依赖 WASM**；但**无现成 weaponized exp**，需自研 addrof/fakeobj + 任意读写 + ASLR 绕过 |
| 2021 在野 V8 链：21148 / 30551 / 30563 / 37975 / 38003 / 4102 | 全部「< 各自修复版本」 | ✅ 只要目标 build 早于修复版就在范围内；**均缺现成可用 exp** |
| `allpaca/chrome-sbx-db`（沙箱逃逸 PoC 库） | **全部 ≤ M-83** | ❌ **不适用** —— 绝大多数是 `MojoJS POC`，而 **MojoJS 需要特权启动标志（`--enable-blink-features=MojoJS` 类）才能从网页触达**，服务端不会开 |
| **`dmbs335/the-map` §9** HTML-to-Document Conversion RCE | — | ★ **当检验清单用**（见 §4） |

**判据小结**：**「有没有公开 PoC」不等于「能不能用」** —— 必须逐条核对
① 版本是否落在受影响区间 ② 它依赖的原语（WASM / SAB / MojoJS / 特定 flag）在本目标是否可用。

---

## §4 检验清单：HTML→PDF 服务的五条 RCE 路径（来源 the-map §9，逐条判定）

| # | 路径 | 判定要点 |
|---|---|---|
| 1 | `--no-sandbox` + `file://` 读本地文件 / iframe 读云元数据 | Chromium 策略是否拦 `file://`（**与沙箱无关**）；SSRF 是否出网 |
| 2 | 浏览器内存破坏 → 逃逸 | 见 §2 的 ②③④ + 沙箱状态 |
| 3 | JS SSRF → 打内部服务（Redis/元数据）→ RCE | 出网 + localhost 端口可达性（CDP 9222 优先）；⚠️ **Chrome 已移除 gopher://**，XHR 打 Redis 这类非 HTTP 服务不可行 |
| 4 | PHP PDF 库注入（dompdf `@font-face` 写 .php / TCPDF 字体元数据 / Phar 反序列化） | **仅 PHP 栈**；Node+Chromium 栈直接 N/A。参考 CVE-2022-28368 / CVE-2024-56520 |
| 5 | 单遍过滤器绕过（`<ifraiframeme>` → `<iframe>`） | **仅当存在清洗器**；无清洗器则 N/A。参考 **CVE-2025-0474**（Invoice Ninja ≤5.10.43：单遍 `str_ireplace` 绕过 + Chromium `--no-sandbox` ⇒ SSRF + 任意文件读）|

---

## §5 工程约束（不知道就会白干一轮）

1. **PDF 生成时机** —— `page.pdf()` 常在 **0.5~1s** 内触发（`waitUntil: load` / 固定延迟）。
   ⇒ **异步探测结果会被丢弃**。回读型载荷**必须同步写 DOM**（同步 XHR，或直接 `document.write`）。
2. **输出编码** —— Chromium 的 PDF 用 **Identity-H + ToUnicode CMap**，`[<hex>] TJ` / `<hex> Tj` 形式。
   字符集稍偏就可能**丢字**（亲例：`navigator.userAgent` 用普通文本输出被截成 `IE`，改 **hex 字符码**输出才完整）。
   ⇒ **要回读的内容一律转 hex 字符码输出**。

   ★ **自建 PDF 文本提取器的两个坑（2026-09-18 亲踩，写完必须回归测试）**：

   | 坑 | 现象 | 正确做法 |
   |---|---|---|
   | **「取含 `BT` 的最大流当内容流」** | 内嵌字体二进制里**恰好也含 `BT` 字节**；单字体小页面时字体流（20KB+）比内容流（几百字节）大 ⇒ 内容流被跳过，**提取结果为空**（看起来像"PDF 里没文字"） | 按 **`/Type /Page` → `/Contents`** 精确定位内容流；兜底筛选时排除以字体魔数（`\x00\x01\x00\x00`/`OTTO`/`true`/`ttcf`）开头的流 |
   | **按「映射表最大值」推码宽** | Identity-H **子集字体的字形 ID 常 < 0x100**，会被误判成 1 字节 ⇒ 逐字节解码，**每个字符前多一个 `?`**（`?C?O?M?P?...`） | 码宽取自 CMap 的 **`begincodespacerange <0000> <FFFF>`**（=2 字节），其次看字体声明 `/Identity-H`、`/Type0`；**绝不能用 max(cmap)** |
   | 多个字体的 ToUnicode 合并成一张表 | 多字体页面串码 | 按 **`/Fx Tf` 跟踪当前字体**，用该字体自己的 CMap |

   **回归纪律**：改完提取器，必须把之前几轮的 PDF 全部重跑一遍，确认**历史结论不变**（本次回归了 `r36_R1`/`r5b_run`/`r28_selfcheck`/`r31_prereq`）。
   ⇒ 提取器是证据链的一环，它出错会**同时**产生假阳性和假阴性（真阴性看起来像"没渲染出文字"）。
3. **WAF 内容检查** —— 载荷里出现 `file://`、`passwd`、`meta-data` 这类串可能被 WAF 直接拦。
   ⇒ **在运行时用字符串拼接生成**（`"fi"+"le:"+"///etc/ho"+"stname"`）绕过内容匹配。
4. **`file://` 在子资源路径上会打崩浏览器实例**（顶层导航不会，见 §8）—— 见 §6。
5. ★ **页面内的「检测型载荷」必须先自证有效（加负对照）**（2026-09-18 亲踩）：
   用 canvas 宽度探测已装字体时，若写 `measureText` 于 `72px FontName` 再与通用族比，
   **字体缺失会回退默认字体 ⇒ 全部误报"存在"**（本次 14/14 假阳性）。
   正确做法：比 `72px 'FontName', <generic>` 与 `72px <generic>` 的宽度差，**并同时探测一个必定不存在的字体名作负对照**——
   负对照若也报"存在"，说明方法坏了。**同类检测（字体、插件、编解码器、API 能力探测）都适用这条。**
6. **`navigator.connection` 在 headless 下是默认值**（`type=4g rtt=0 downlink=10`），**不是真实网络测量**，别当结论写。

---

## §5.5 能从服务端读到的信息（实测清单，可直接复用作「服务端信息收割」模板）

| 类别 | 取法 | 亲例实测值 |
|---|---|---|
| 系统时区 | `Intl.DateTimeFormat().resolvedOptions().timeZone` + `new Date().toString()` | `Asia/Shanghai` / `GMT+0800` |
| GPU | `getExtension('WEBGL_debug_renderer_info')` → `UNMASKED_RENDERER` | **`Google SwiftShader`** ⇒ 无显卡容器 |
| 镜像构成 | canvas 字体探测（**带负对照**）| 有 Liberation/Noto CJK/WenQuanYi，**无 DejaVu** ⇒ 裁剪镜像 |
| 视口/屏显 | `screen` / `innerWidth` / `devicePixelRatio` | `800x600` DPR=1 ⇒ 未改 headless 默认 |
| 硬件 | `hardwareConcurrency` / `deviceMemory` / `performance.memory` | 64 核 / 8GB / 3.76GB 堆 |
| **自动化痕迹** | `navigator.webdriver` / `typeof window.chrome` | **`true`** / `undefined` |
| **页面加载机制** | `performance.getEntriesByType('navigation')[0].name` + `resource` 条目数 | 导航到**随机伪造域**、**资源条目 0** ⇒ 子资源被整体掐断（解释了 OOB 零命中）|
| HTTP 层 | 响应头 | `/print` 回 **`Server: AliyunOSS`** + `x-amz-request-id` ⇒ 落 OSS 后透传对象响应 |

**读不到的**：宿主机文件（`file://` 被浏览器策略拦）、`/proc`/环境变量/进程、内网与元数据（DNS 隔离 + CDP 不可达）、出网。
⇒ 结论：**能做「环境与镜像指纹」级别的信息读取，不能做「文件/内网/进程」级别的读取。**

---

## §6 ⚠️ 安全边界：`file://` 在**子资源**路径上会销毁浏览器实例（**已修正，见 §8**）

**一个** `<img src=file:///…>` 子资源（或对 `file://` 的同步 XHR）就会让 Puppeteer 的 `browser` 对象 disconnect：

```
error-page url: html/<host>/<date>/<ts>-<rand>.oss.html,
message: Navigation failed because browser has disconnected!
```

- **单发、0.36~0.5s** 即可触发 ⇒ 说明服务**在渲染失败时会销毁整个浏览器实例**（而非复用）。
- **但通常自愈很快**（亲例 0.8s 后 `/health` 200 + `POST /print` 200 + `%PDF-`）
  ⇒ **实测常不构成可利用的 DoS**，别急着按 DoS 报。
- ★ **「禁止 DoS」是绝对红线（无例外）：一律不复现、不武器化，用户同意也不做。**
  记录现象即可，并明确写「未做持续发送验证」。
- ⚠️ **做任何 file:// 相关测试前先问自己：这一发会不会把目标打掉？** 会 ⇒ **不做**。

---

## §7 一页速用（复制即用）

```js
// 渲染上下文自检（同步写 DOM，hex 输出，避开字体丢字 + 异步丢结果）
var S=""; function R(k,v){S+=k+"|"+v+"\n";document.getElementById("o").textContent=S;}
function HEX(s){var o=[];for(var i=0;i<s.length;i++)o.push(s.charCodeAt(i).toString(16));return o.join(" ");}
R("CTX", typeof process+"/"+typeof require+"/"+typeof module+"/"+typeof global+" | win="+(typeof window));
R("WASM", typeof WebAssembly);
R("SAB", (function(){try{new SharedArrayBuffer(8);return "OK"}catch(e){return "FAIL "+e.name}})());
R("EVAL", (function(){try{eval("1");return "ok"}catch(e){return "BLOCKED "+e.name}})());
R("UA_HEX", HEX(navigator.userAgent));
R("VENDOR", navigator.vendor);
R("ORIGIN", location.origin);
R("COI", String(typeof crossOriginIsolated!=="undefined"?crossOriginIsolated:"undef"));
// 出网/内网（同步 XHR，逐个试；注意 file:// 会打崩浏览器 ⇒ 不要试 file://）
["http://127.0.0.1:9222/json/version","http://127.0.0.1:9515/status"]
 .forEach(function(u){ try{ var x=new XMLHttpRequest(); x.open("GET",u,false); x.send();
    R("NET:"+u, "status="+x.status+" len="+(x.responseText||"").length); }
   catch(e){ R("NET:"+u, "ERR "+e.name); } });
```


---

## §8 `file://` 的两条路径实测差异（2026-09-18 补充，修正 §6 的过度概括）

| 路径 | 实测结果 |
|---|---|
| **子资源**（`<img>` / `<iframe>` / 同步 XHR） | 404 + `browser has disconnected` ⇒ **Service 销毁整个浏览器实例**（0.36~0.5s，0.8s 自愈）|
| **顶层导航**（`<meta http-equiv=refresh>` → `file://`） | **200 + 正常 PDF**，页内标记保留、**未出现被读文件的内容**，**未销毁浏览器实例**；`/health` 复检 200 |

**推论**：
1. 「`file://` 就会打崩浏览器」是**过度概括** —— 该现象只在**子资源**路径观察到。
2. 但**两条路径都拿不到本地文件**：子资源被 Blink 挡；导航要过更严的 `CanCommitURL`，而 `file` 不是 web-safe scheme。

**残留不确定性（诚实标注）**：meta-refresh 那一发**无法区分**「导航被浏览器静默取消」与「refresh 未触发」——
两种情况页面快照完全相同。要区分需再发一发 `location.href` 赋值型导航。
**不要**为消除这点不确定性去穷举变体：收益极低，且**子资源路径每发都会销毁一个浏览器实例**。

**纪律**：`file://` 相关实验一律**单发 + 发后复检 `/health`**，一发现销毁现象立即停手；
禁止并发、禁止「持续发送看能否维持不可用」。

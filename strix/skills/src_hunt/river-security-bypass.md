---
name: "river-security-bypass"
description: "river-security-bypass"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# river-security-bypass

# 瑞数（RiverSecurity / Botgate）动态防护绕过

> **定位**：`waf-bypass-parser-layer.md` §9 已判定「动态 JS 防护 ≠ 静态 WAF」并给出方向；
> 本模块是那条方向的**实操篇** —— 怎么识别版本、三件套是什么、四条技术路线怎么选。
>
> **本文 100% 基于两类来源**（不掺猜测）：
> ① 2026-09-14 对 **189.cn 的实测**（标注 `[实测]`）
> ② 公开技术文章 / 开源工具（标注 `[资料]`，链接见 §9）
>
> ⚠️ 合规：本模块用于**授权**安全研究。补环境/RPC 只用于让自动化请求能正常访问
> **你本就有权访问**的页面，不用于绕过业务鉴权。

---

## 1. 一分钟心智模型

瑞数 = **动态代码下发 + VMP 虚拟机 + 环境指纹采集**。核心思想：
**每次访问下发的 JS 都不同**，让你没法对固定代码逆向复用。

```
首次请求
   │
   ├─ 服务端返回 412 + 一段「每次都不一样」的挑战页
   │     ├── $_ts.cd   （加密配置，>1000 字符）
   │     └── <script src="/<随机8位>/<随机文件名>.<构建号>.js">   ← VMP JS
   │
   ├─ 浏览器执行 VMP JS
   │     ├── 采集环境指纹（navigator/screen/chrome 对象/时序/CRC）
   │     ├── 计算并写入 **Cookie2**
   │     └── hook XHR.open，向请求 URL 注入 **动态后缀参数**
   │
   └─ 带着三件套重新请求 → 200
```

**三件套，缺一即 412**（这是全篇最重要的结论）：

| # | 名称 | 谁产生 | 值特征 | 189 实测对应 |
|---|------|-------|--------|-------------|
| 1 | **Cookie1** | **服务端 Set-Cookie 下发** | 值 80~100 字符，**首字符 = 版本号**（`6`=瑞数6 / `5`=瑞数5） | `EYg4xOZq0mLeS=60sgFS_...` → **首字符 6 = 瑞数 6** |
| 2 | **Cookie2** | **VMP JS 在浏览器算出并 `document.cookie` 写入** | 值 300~500 字符，**名字与 Cookie1 前 12 位相同、仅末位不同** | `EYg4xOZq0mLeT=0qCdH3TMFC3WrrfzO4lyPbfk...` |
| 3 | **URL 后缀参数** | **VMP JS hook `XMLHttpRequest.open` 注入** | `?<8位随机名>=<值>`，部分站点才有 | `?JEbLzrb5=0i4HmMAEqWrp...` |

> **三件套是独立校验的**（`[资料]` 明确指出：「与 Cookie1、Cookie2 是完全独立的第三个校验参数」）。
> 所以只补 Cookie 不够，**必须连 URL 后缀一起生成** —— 这是最容易漏的一环。

---

## 2. 识别与版本判定（30 秒）

### 2.1 是不是瑞数

**同时满足以下两条即判定为瑞数**（`[资料]` 给的判据，`[实测]` 在 189 上完全吻合）：

1. HTML 第一个/第二个 `<script>` 里有 `$_ts` 赋值，且 **`$_ts.cd` 内容 > 1000 字符**
2. 页面有一个 `src` 指向**路径和文件名都是随机串**的 JS（带固定构建号后缀）

```
# 189 的 412 挑战页原文片段 [实测]
<meta id="3etE7dr7M7O6" content="<每次不同>" r='m'>
<script r='m'>$_ts=window['$_ts'];if(!$_ts)$_ts={};$_ts.nsd=13987;$_ts.cd="qERJrrQlEPElqcVmEGWqxAA...";if($_ts.lcd)$_ts.lcd();</script>
<script r='m' src="/dRzdEobEkKpR/uc2w802ahCzY.27ac2b3.js"></script>
<script r='m'>_$$q();</script>
```

**注意 `[实测]` 的一个坑**：同一次会话里抓到的 VMP JS 文件名是
`ozSctocr7Ph9.27ac2b3.js`，而另一个 412 页面里是 `uc2w802ahCzY.27ac2b3.js` ——
**目录名（`dRzdEobEkKpR`）与构建号（`.27ac2b3`）稳定，文件名随机**。
**所以做缓存必须以完整 URL 为键**，不要硬编码文件名。

### 2.2 版本判定（看 Cookie1 值的首字符）

| Cookie1 值首字符 | 版本 | 备注 |
|---|---|---|
| `6` | 瑞数 6 | 可能是 VMP（纯 JS）或 VMP+WASM |
| `5` | 瑞数 5 | |
| `4` | 瑞数 4 | 更早，字符串混淆为主 |

**`[实测]` 189 = 瑞数 6**（Cookie1 值 `60sgFS_...` 首字符 `6`）。

### 2.3 附加特征：是否含 WASM / SM4

`[实测]` 对 189 的 VMP JS（274KB）做关键字扫描：

```
$_ts: 6 次   cp: 3 次   lcd: 2 次   nsd: 2 次   debugger: 1 次
SM4: 0 次    WebAssembly / wasm: 0 次
唯一变量名: 72 个 _$xxx 形式
字符串常量: 几乎为空（全部编码进字节码）
```

→ **189 是纯 JS 的 VMP 形态**（无 WASM、无 SM4），字节码解释器特征明显：

```js
// 189 VMP JS 开头 [实测]
if($_ts.cd){
(function(_$iF,_$mm){var _$db=0; ... 
  var _$b7,_$jR,_$aF=_$db,_$mt=_$mm[0];
  while(1){_$jR=_$mt[_$aF++];              // ← 字节码解释器主循环
    if(_$jR<12){ if(_$jR<4){ ... } } ...
```

> 有些资料说「瑞数 6 = WASM + SM4」，**189 证明不成立** ——
> 版本号与是否上 WASM 是两个独立维度，**要实际扫关键字才知道**。

### 2.4 状态码语义

| 码 | 含义 |
|---|---|
| **200** | 三件套有效 |
| **412** | 缺/无效瑞数 Cookie → 需要重新走挑战 |
| 202 | 部分站点的拒绝码，语义同 412 |
| **400** | `[实测]` 189 在全新技术栈/全新 profile 上出现 —— 语义是「Cookie 存在但校验不过」，**不是挑战没有** | 
| 493 / 403 | 频率过高被限流/封禁 |

**关键区分（`[实测]` 踩过的坑）**：
- **412 = 需要执行挑战 JS**（挑战页有 2500+ 字符 HTML）
- **400 = 挑战层已放行，但校验不过**（响应是**空 HTML，39 字符**）

看见 400 别再去找挑战页，那是**会话/指纹**问题。

---

## 3. 四条技术路线（按性价比排序）

| 路线 | 原理 | 成本 | 稳定性 | 需要什么 |
|------|------|------|--------|---------|
| **A. 中间人 / 浏览器请求转发** | 请求发给**真实浏览器**执行，浏览器回传响应 | **低** | 高（不碰算法） | 用户装扩展或开 CDP |
| **B. 补环境（Node.js）** | 在 Node 里复现浏览器环境，跑 VMP JS 算出 Cookie2 + URL 后缀 | 中 | 中（瑞数更新即失效） | Node + 逐项补环境 |
| **C. 引擎级指纹伪装** | 改浏览器引擎源码，让指纹由引擎产生而非注入 | 中高 | 高 | 编译过的 Firefox / `invisible_playwright` |
| **D. 纯算法还原** | 反混淆 VMP、还原 `$_ts` 与算法 | **高** | 低（每站要适配） | 逆向功底 + 适配文件 |

**选型口诀**：
**能上真实浏览器就别补环境；能用打过补丁的浏览器就别读字节码。**

---

## 4. 路线 A：中间人 / 浏览器请求转发（首选）

### 4.1 riverPass（Go，`[资料]`）

**仓库**：`github.com/wjlin0/riverPass`（`sv3nbeast/riverPass` 是其 fork）。
**原理**：用 WebSocket 把请求送进**你自己浏览器**里执行 —— 浏览器已过瑞数，于是绕过检测。

**`[资料]` 给出的关键信息**：README 的示例**直接用 `www.189.cn`**

```bash
riverPass -pp 8081                                   # 起代理
riverPass -dw www.189.cn,www.example.com             # 域名白名单（只允许指定域重放）
```

流程：
1. 跑一次 `riverPass`，它会生成 mitmproxy 证书（在 `$HOME/.mitmproxy`），**导入证书**
2. 浏览器代理指向 Burp/Yakit；Burp/Yakit 下游代理指向 riverPass
3. 访问一次目标站（README 示例就是 `https://www.189.cn/sc/`）
4. 在 Burp 里对某个包重放时**加请求头 `Req-Flag: 1`** → 该请求被转发到浏览器执行

编译需 **go1.23**：`go install -v github.com/wjlin0/riverPass/cmd/riverPass@latest`
（有 Windows 预编译二进制）

**借鉴来源**：`R0A1NG/Botgate_bypass`（同思路的更早实现）。

### 4.2 CDP 直连真实 Chrome（`[实测]`：**不一定够，需谨慎**）

思路：用户用 `chrome.exe --remote-debugging-port=9222` 启动，我们用 CDP
（`agent-browser connect 9222`）在真实上下文里发请求。

**`[实测]` 结论（2026-09-14，189.cn）**：

```
全新 profile + CDP   →  https://www.189.cn/web/  返回 400，空 HTML（39 字符）
                        document.cookie 只有 Cookie2(T)，无 Cookie1(S)
同源 XHR 复测        →  400（不是 412）
```

**判读**：CDP 连接下**瑞数挑战层其实放行了**（否则该是 412 挑战页），
但**缺少 Cookie1 且 Cookie2 不被认可** → 400。

**可能原因（未逐一验证）**：
- **全新 profile 无会话历史**，指纹"太干净"
- Cookie1 是服务端下发，但**新 profile 首次访问没拿到**（或拿到了却与 Cookie2 不配对）
- CDP 存在本身可被检测

**所以**：CDP 方案要成立，**必须用用户日常 profile**（有历史会话、有扩展、有正常指纹），
而不是全新 profile。这一点务必先验证，否则白做一轮。

### 4.3 判据（别自欺）

**成功 = 目标接口返回真实业务数据**。
返回 400/404 只说明"过了挑战层"，**不等于绕过**（与 `waf-bypass-parser-layer.md` §2.1 同一判据）。

---

## 5. 路线 B：补环境（Node.js）—— 最通用的自动化方案

> 来源：CSDN《从412到200:瑞数6动态防护的Node.js补环境逆向实录》（`[资料]`，见 §9）。
> 这是我找到的**最完整、最可直接照做**的一份方案。

### 5.1 架构

```
Python (xxx.py)
   └─ subprocess.run(['node', '04_main.js', 'gen_cookie'])
        04_main.js
          ├─ require('./01_env.js')     # 浏览器环境模拟
          ├─ require('./02_ts.js')      # 动态 $_ts 代码块（每次从页面提取）
          └─ require('./03_source.js')  # 动态 VMP JS（每次从页面下载）
```

Python 侧拿 Node 产出的 Cookie + URL 后缀，再发真正的业务请求。

### 5.2 必须补的环境对象（照抄清单）

| 对象/属性 | 补法 | 为什么 |
|---|---|---|
| `window` | `window = global` | VMP 全篇在 window 上跑 |
| `window.top` / `window.self` | 同 window 引用 | 框架检测 |
| `window.innerWidth/Height` | 固定值（如 1920/983） | 屏幕尺寸指纹 |
| `window.outerWidth/Height` | 固定值（如 1920/1040） | 窗口尺寸指纹 |
| **`window.chrome`** | **完整对象**：`loadTimes` / `csi` / `app` | ⚠️ **`loadTimes()` 要有完整返回结构**（含 `connectionInfo`、`npnNegotiatedProtocol`），空函数会导致指纹算错 |
| `window.addEventListener` | 空函数 | 阻止事件绑定报错 |
| `window.setInterval/setTimeout` | 空函数 | 阻止定时器运行 |
| `window.name` | `''` | 默认值 |
| `window.MutationObserver` | 返回带 `observe` 的对象 | 阻止 DOM 监听 |
| `window.fetch` / `Request` | 返回空对象的函数 | 阻止内部请求 |
| `document.cookie` | 注入 cookie 字符串 | VMP 会读 cookie 参与计算 |
| **`navigator.userAgent`** | **与请求头 UA 完全一致** | ⚠️ 不一致必挂 |
| **`navigator.webdriver`** | `false` | 规避自动化检测 |
| `localStorage` / `sessionStorage` | 实现 Storage 类（`getItem/setItem/clear`） | 存在性 + 读写行为检测 |
| `XMLHttpRequest` | 空实现 | 阻止内部请求（**但要 hook `open` 抓 URL 后缀**，见 5.3） |
| `HTMLAnchorElement` 等 | 空函数或 debugger | 防止构造函数调用报错 |
| **`__dirname` / `__filename`** | **`delete` 掉** | Node 专有变量会被检测 |

### 5.3 ⚠️ URL 后缀机制（最容易漏，也最可能正是你的 412 原因）

**部分站点**在 VMP JS 执行期间，会通过 `XMLHttpRequest.open` 把一个
**独立动态参数**嵌进请求路径：

```
VMP JS 内部调用  XMLHttpRequest.open("POST", "/path/to/api?key=value...")
        ↓
04_main.js 里 hook 了 open，把带后缀的路径存下来  →  req_url
        ↓
Python 调  get_suffix_url(original_url)  →  返回拼接后缀的完整 URL
        ↓
Python 用**带后缀的 URL**发请求   ← 不带服务端就拒
```

**实测对应（189）**：所有业务接口 URL 都带 `?JEbLzrb5=<长串>`，
例如 `.../queryUserFlag.do?JEbLzrb5=0i4HmMAEqWrp...` —— **这就是第三个校验参数**。

**顺序要求（`[资料]` 强调）**：`get_suffix()` **必须在 `require('./02_ts')` 之前调用**，
确保在 VMP JS 开始执行前就完成 hook。

**启用时机**：「当请求接口返回 412 且**确认 Cookie 正确**时，才需考虑启用后缀机制」。
（大多数站点没有后缀机制，直接读 `document.cookie` 即可。）

### 5.4 两个反直觉的坑

1. **不要格式化 VMP JS**。`[资料]`：用 Prettier 格式化会**直接导致验证失败**
   （瑞数检测代码格式特征）。必须以原始缩进换行保存。
2. **文件编码必须是 UTF-8 without BOM**。Windows 下 BOM 头会导致验证失败。

### 5.5 `content` 字段要不要注入

页面里除 `$_ts` 外常有 `content` 字段。`[资料]`：**大多数站点的 VMP JS 不读它**，
不注入也能出 Cookie。**先不注入直接跑**；只有报错提到 `window.content` 再按需注入。
加载顺序变为 `01_env.js → 06_content.js → 02_ts.js → 03_source.js`。

---

## 6. 路线 C：引擎级指纹伪装

**`bivex/firefox_antidetect_patch`**（`[资料]`）：在 **C++ 源码级**打补丁，
让指纹**由引擎产生**而不是往页面里注入脚本。

**为什么要在引擎层做**（`[资料]` 的原话，值得记）：
> 「注入的脚本必须跑在页面里，页面就能找到它。」—— hook 的函数能被 `toString()` 打印出来，
> 它返回的值能被和另一个没一起改的值对比，worker/iframe 可以在补丁没覆盖的上下文里问同样的问题。
> **在引擎里改是「消除接缝」，而不是「把接缝藏起来」。**

**补丁覆盖的 surface**：navigator 与 UA、屏幕几何、WebGL vendor/renderer 字符串及其数值上限、
canvas 像素输出、字体集、音频管线、WebRTC ICE candidates、时区、locale、代理路径。
**所有值通过 preference 注入**（不硬编码在 C++ 里），一个 seed 复现一台机器。

**衍生产品（多数人直接用这两个，而不是这个仓库）**：
- **`invisible_playwright`** —— Python 包装，用标准 Playwright API 驱动
- **`invisible_firefox`** —— 多身份 profile 管理器

**注意**：该构建每次启动会发一个匿名计数 GET（`invisible_firefox.usage_ping.enabled`
可关，或删 `BrowserGlue.sys.mjs` 里的对应块后重编译）。
安全研究环境里建议关掉，避免无关外带流量。

---

## 7. 路线 D：纯算法还原（rs-reverse）

**`go-laoji/rs-reverse`**（`[资料]`，npm 包名 `rs-reverse`）：**瑞数 vmp 纯算法逆向**工具。

### 7.1 四个子命令

| 命令 | 作用 |
|---|---|
| `makecode` | 还原 `$_ts`：输出原始 `$_ts`、外层虚拟机生成的 `$_ts`、静态文本、**内层虚拟机代码（dynamic.js）** |
| `makecookie` | 生成 Cookie |
| `makecode-high -u <url>` | 高阶还原（带 URL 自动取） |
| `exec -c 'gv.cp2'` | 在还原出的上下文里执行表达式 |

用法：`npx rs-reverse makecode` 或 `node main.js makecode`。

### 7.2 适配新站点要填的参数

在 `src/handler/basearr/` 下新增适配文件，底部写：

| 参数 | 含义 |
|---|---|
| `adapt` | 目标 hostname 数组（为减少明文，需 `simpleCrypt` 加解密处理） |
| `encryptLens` | **第一层加密后的数组长度**（网站时间/随机数不同会算错，程序会多次尝试） |
| `hasDebug` | 生成内层虚拟机代码是否加额外 debugger 文本（默认两处 debugger） |
| `lastWord` | **cookie 键的最后一个字母**，来自 `$_ts.cp[0]`；默认 `T`，已知有 `T` 和 `P` |
| `flag` | **4 位数字，每个网站不同**，疑似瑞数给客户网站的序列号 |

> **189 实测数据**（`[实测]`）：`lastWord = 'T'`（Cookie2 名 `…mLeT`），与默认值一致；
> `hostname = www.189.cn`。`encryptLens` / `flag` 需实际跑才知道。
> **⚠️ 但 189 的问题不在这些参数上 —— 见 §7.5，框架根本不支持 189 的 rs 版本。**

### 7.3 官方已适配站点（供参考，`[资料]`）

`riversecurity.com`（厂商官网）、`epub.cnipa.gov.cn`、`zhaopin.sgcc.com.cn`、
`njnu.edu.cn`、`ems.com.cn`、`jf.ccb.com`、`customs.gov.cn`、`fangdi.com.cn`、`nmpa.gov.cn`

**已知坑（`[资料]` 备注）**：`njnu.edu.cn` 直连返明文，**加代理后才返加密密文**
（怀疑与请求头参数有关）—— 说明**代理链路本身会影响瑞数的加密行为**，测的时候要固定链路。

### 7.4 其他逆向案例库

`0xAllenChen/spider_reverse`（`[资料]`）：爬虫逆向案例合集，含
**TLS 指纹 / 瑞数（`2024-4` 目录「dp通过瑞数4」）/ 网易易盾 / 加速乐 / 极验滑块 /
微信小程序反编译 / rpc 解密** 等 20+ 案例。适合当**案例索引**查，不适合当框架用。

### 7.5 `[实测]` rs-reverse 跑 189.cn 的完整结论：makecode 通，makecookie 不通

**环境**：npm `rs-reverse@1.16.3`，Windows + Node 22。
（注意：**npm 上的作者是 `pysunday`**，不是资料里写的 `go-laoji` —— 后者可能是 fork 或旧名。）

| 实验 | 结果 |
|---|---|
| `makecode`（自带样例，验证工具本身） | ✅ 183ms |
| `makecookie -u https://www.riversecurity.com/`（**官方已适配站 = 对照组**） | ✅ 568ms，生成 236 字符 cookie |
| `makecode -u https://www.189.cn/web/` | ✅ 290ms，产出 `ts-full.json` / `immucfg.json`(607KB) / **内层虚拟机代码** / `-dynamic-pure.js` |
| `makecookie -u https://www.189.cn/web/` | ❌ 报错 |
| `makecode-high -u https://www.189.cn/web/`（**作者官方的 cookie 可行性验证命令**） | ❌ 同错 |

**对照组通过** → 环境/链路无问题，**失败是 189 特有**。

**189 挑战页实测参数**（实时抓取）：

| 项 | 值 |
|---|---|
| `$_ts.nsd` | `11928`（每次不同） |
| `$_ts.cd` 长度 | **1728** |
| VMP JS 路径 | `/dRzdEobEkKpR/uc2w802ahCzY.27ac2b3.js`（目录 12 字符 + 文件名 12 字符，**每次不同**；**版本号 `27ac2b3` 固定**） |
| 框架自动判定 | 「**额外 debugger 版本**」（靠内层代码含 `push("gger;")` 识别） |

> 版本号固定、目录/文件名随机的规律**可用于跨会话指纹识别**：同一站在防护配置不变时版本号稳定。

**★ 关键判定：不是「缺 basearr 适配」，而是「框架不支持 189 的 rs 版本」。三条证据：**

1. 把 **7 个内置适配器（lens 103/123/127/133/157/163/166）全部**轮流挂上 `www.189.cn`
   跑 `makecookie`，**全部失败**，且失败点各不相同。
2. **同一配置连跑 3 次**（不改任何东西），失败点也**各不相同**
   （`TypeError: Cannot set properties of undefined (setting 'undefined')` /
   `(setting '1')`）→ 失败**只跟每次抓到的随机挑战有关**，与适配器无关。
3. **失败位置在 `parser.init`（解析 `$_ts.cd`）里**，而 basearr 的生成
   `getBasearr()` 在 `parser.init` **之后**才执行（`Cookie.js:21` → `Cookie.js:29`）
   → **basearr 适配根本救不了这个错。**

要救得把框架**移植到 189 的 rs 版本**（`tscd.js` 硬编码的任务 uid `U14124020`、
`cd` 解密布局、`genKeys` 步进都要跟着改）——比作者说的「适配一个站约 1 天」更重。

**⭐ 由此得到一条路线取舍结论（重要）**：

适配 rs-reverse 的**第一步，就是拿一次真实浏览器里生成的 basearr 当对照**
（适配器的 `example` 字段就是干这个用的）。
也就是说 —— **纯算法路线的前提，与中间人路线的前提完全重合**（都得先有一次能过挑战的真实浏览器会话）。
**既然已经拿到浏览器会话，中间人（§4）当场就能打；纯算法只是把「一次性能力」变成「可复用能力」。**
→ **在还没有任何浏览器会话时，不要从纯算法入手**；它是「能力沉淀」阶段的选项，不是「突破」阶段的选项。

**另一条 Windows 专属坑（会白费半小时）**：`utils/isValidUrl.js` 用 `new URL(url)` 判断，
而 Node 认为 `C:/path` 是合法 URL（把 `c:` 当协议名）
→ **`-j <本地文件路径>` 在 Windows 上永远被当成远程 URL**，报
`RequestError: Invalid URI "c:/…"`。**绕法：统一用 `-u <挑战页URL>` 让工具自己抓。**

---

## 8. `[实测]` 案例：189.cn（2026-09-14）

| 项 | 结果 |
|---|---|
| 版本 | **瑞数 6**（Cookie1 值首字符 `6`） |
| 形态 | **VMP 纯 JS**（无 WASM / 无 SM4），274KB，72 个 `_$xxx` 变量 |
| Cookie1 | `EYg4xOZq0mLeS=60sgFS_…`（服务端下发，全程不变） |
| Cookie2 | `EYg4xOZq0mLeT=0w6nWbQX…` → 中途变为 `0qCdH3TM…`（**JS 动态更新**） |
| 第三个 cookie | `EYg4xOZq0mLeO=…`（服务端 Set-Cookie 下发，`HttpOnly`） |
| URL 后缀 | `?JEbLzrb5=<长串>`（每个接口都有，名固定 8 字符） |
| 豁免面 | 仅 `/wtBusiness/wtservice/nc/recPos/getRecPosInfo.do` 返回 200；**静态资源全豁免** |
| 纯 HTTP 直连 | 21 个接口全 412（除 recPos） |
| 全新 profile 浏览器 | `www.189.cn/web/` → **400 空 HTML**，只有 Cookie2，无 Cookie1 |
| 同源 XHR | 400（不是 412） |
| 挑战页参数 | `nsd=11928`（每次不同）、`cd` **1728** 字符、VMP JS `/dRzdEobEkKpR/uc2w802ahCzY.27ac2b3.js`（**版本号 `27ac2b3` 固定**） |
| `rs-reverse makecode` | ✅ **成功**（290ms，解出内外层虚拟机代码） |
| `rs-reverse makecookie` | ❌ 失败；7 个内置适配器全试 + 同配置 3 次重复**失败点随机** → **框架不支持 189 的 rs 版本**（见 §7.5） |

**从这份实测得出的三条操作性结论**：

1. **"过了挑战层"与"能用"是两回事** —— 400 说明挑战层放行了，但三件套没配齐。
   排查顺序：**先查 Cookie1 有没有拿到 → 再查 Cookie2 是否被认 → 最后查 URL 后缀**。
2. **全新 profile 不可靠** —— 要走浏览器路线，必须用**有历史会话的日常 profile**；
   要长期自动化，走**补环境（§5）**更可控。
3. **纯算法（rs-reverse）不能当突破口** —— 它自身就要用「一次真实浏览器 basearr」做对照，
   前提与中间人重合（§7.5）。**先中间人打通，再考虑要不要沉淀成算法。**

---

## 9. 决策树

```
目标返回 412 + $_ts 动态挑战页
│
├─ 只是想「手工/半自动地打这个站」？
│   └─ 走【路线 A】：riverPass 中间人（§4.1）或 日常 profile + CDP（§4.2）
│       判据：目标接口返回真实业务数据（不是 400/404）
│
├─ 想做成可复用的自动化请求（脚本/扫描器）？
│   └─ 走【路线 B】补环境（§5）：
│        ① 抓 412 页 → 存 02_ts.js（原样，禁格式化，UTF-8 无 BOM）
│        ② 下载 VMP JS → 存 03_source.js（以完整 URL 为缓存键）
│        ③ 按 §5.2 清单补 01_env.js（重点：window.chrome / navigator.webdriver / UA 一致 / delete __dirname）
│        ④ **先 hook XHR.open 拿 URL 后缀**，再 require 02_ts
│        ⑤ 读 document.cookie 取 Cookie2，与 Cookie1 拼齐
│        ⑥ 用「Cookie1+Cookie2+带后缀 URL」发业务请求
│
├─ 高对抗 / 长期跑，不想每次补环境？
│   └─ 走【路线 C】：invisible_playwright（引擎级指纹，§6）
│
└─ 只想彻底搞明白算法 / 目标很长期？
    └─ 走【路线 D】：rs-reverse 适配（§7），接受「瑞数一更新就重做」的成本
       ⚠️ 但它**不能当突破口**：适配本身就需要一次真实浏览器 basearr 做对照（§7.5），
          前提与路线 A 重合。**先用 A 打通，再决定要不要沉淀成 D。**

**任何路线的验证门槛都是同一句**：**目标接口返回真实业务数据。**
412→400 不算成功，拿到接口数据才算。
```

### 排查表（412 / 400 不通时按顺序查）

| 症状 | 先查什么 |
|---|---|
| 一直 412 | 挑战 JS 有没有真的执行？Cookie2 有没有写出？（看 `document.cookie`） |
| 412 但 Cookie 看着对 | **URL 后缀有没有带**？（§5.3）→ 是否在 require 02_ts 前 hook 了 open |
| 400 / 202 | Cookie1 有没有拿到？三件套是否**配对**（同一轮挑战产生的）？ |
| 200 但数据空 | 业务层鉴权问题，**不是瑞数问题**了，转常规越权测试 |
| 换环境就挂 | 指纹不一致（UA / screen / chrome 对象），或 VMP JS 被格式化过 |
| 加代理后行为变了 | `[资料]` 已知现象（njnu 案例），**固定链路再测** |

---

## 10. 防守视角（写报告/给甲方建议时用）

| 措施 | 说明 |
|---|---|
| 三件套**同时校验**且互相绑定 | 只校验 Cookie 不校验 URL 后缀，等于留后门 |
| 校验**同轮次**产生 | 允许跨轮次复用 = 会话固定 |
| 指纹项**交叉一致性** | 单独改 UA 能被 screen/screen.availWidth 等反推 |
| 不依赖客户端 JS 做**业务鉴权** | 动态防护只是反自动化，**不能替代服务端鉴权**（这才是 SRC 关注点） |
| 监控异常 | 同一会话内 412/400 高频循环、指纹字段异常（CJK 出现在协议字段位置等） |

> **给 SRC 的落点提醒**：瑞数绕过本身**不是漏洞**（它只是反爬）。
> 绕过之后**在业务层发现的越权/未授权/逻辑缺陷才是**。
> 所以这一整套的价值是「让测试能进行」，而非「报告写瑞数」。
> 唯一例外：**站点把动态防护当成了鉴权**（"过了瑞数 = 已登录"），那才是可报的洞。

---

## 11. 本轮新学到的实操要点（第二批资料，2026-09-14）

> 以下每条都标注了**出处**，便于回溯原帖。都是**原文实际写了**的内容，未做推断。

### 11.1 ★ 后缀有「心跳」，Cookie 与后缀必须配套

来源：《瑞数6 VMP后缀获取全流程：基于Playwright的动态令牌截获实战》

- **后缀是动态计算的**：`?<参数名>=<值>`，参数名每站不同（文中的例子是 `_vq` / `_m`，**189 是 `JEbLzrb5`**）。
  它与 Cookie、UA、浏览器指纹、时间戳都有关联 —— **换环境算出来的后缀就不一样**。
- **★ 后缀和 Cookie 是「配套」的**：原文明确「URL 后缀和 Cookie 是配套出现的，
  后缀里面包含了关键的动态信息，Cookie 里同样有一份对应的校验内容，**服务端会两者一起校验**。
  只带后缀不带 Cookie，或者 Cookie 过期，都可能被判定为异常请求。」
  → **这正是我在 §1 提炼的「三件套」，本文独立印证了一次。**
- **★ 后缀有「心跳」**：原文「VMP 代码往往会在执行完后设置一个**定期刷新任务**，
  每隔几秒或几分钟就重新计算一次后缀。这意味着你捕获到的后缀是有'心跳'的，长时间挂着页面后缀会变。」
  → **这解释了 189 抓包里 `EYg4xOZq0mLeT` 中途变化的观察**。
  → 实操含义：**拿到就用，且设过期时间**（原文实测：有的站几分钟有效，有的十几分钟）。
- **参数过期是最高频报错**，工程做法：**缓存池（默认 5 分钟有效期）**，
  用并发安全的 Map（Go 用 `sync.Map` / `singleflight` 防并发重复抓）。
- **★ 频控阈值**：原文实测「同一份后缀和 Cookie 组合，短时间内在同一 IP 下并发请求
  一般控制在 **5~10 个请求/秒**以内比较稳，超出即使参数有效也可能触发频控。」

### 11.2 Playwright 截获后缀的两种方式（原文给了可运行代码）

来源：同上

| 方式 | 做法 | 适用 |
|------|------|------|
| **网络层监听（首选）** | `page.on("request", cb)`，按关键字过滤目标接口，从 URL 正则提后缀 | 简单可靠，拿到的是浏览器**真正发出**的请求 |
| **注入 Hook（细粒度）** | `add_init_script` 改写 `XMLHttpRequest.open` / `fetch`，记录 URL | 页面请求多、要精确匹配某接口时用；**注意别改坏页面原逻辑** |

**五阶段流程**（原文）：环境初始化 → 访问入口页（等 `networkidle`）→
**触发主动请求**（很多场景后缀不会自己发出去，要点击/调内部函数触发）→ 捕获请求 → 参数落地。

**为什么不用纯 HTTP / Selenium**（原文的选型理由，值得记）：
- **纯 HTTP**：VMP 解释器需要完整浏览器 API（canvas / webgl / 事件循环 / 定时器），
  且瑞数对**环境指纹依赖强** → 纯引擎算出来的结果**大概率过不了服务端校验**
- **Selenium**：指纹特征明显，被识别后容易进「验证码地狱」
- **Playwright**：CDP 控制、自动化特征弱、`add_init_script` 能在页面脚本执行前注入

**★ 不要用物理断点调试 VMP**：原文直说「解释器是一行行跑的，你在某条指令上下断点基本毫无意义，
只会把自己拖进时间黑洞」。

**★ 环境指纹不一致的典型坑**：本地 Windows 跑通，**部署到 Linux 就失效** ——
排查下来是**字体列表差异 + Canvas 渲染差异**。结论：尽量保持部署环境与真实环境接近。

### 11.3 中间人方案的完整实现与**边界**（关键）

来源：`github.com/Tinide/-Botgate_bypass` + 52pojie《另辟蹊径…瑞数"异步"解决方案》

**Botgate_bypass 的架构（纯 Python，比 riverPass 更容易在本机跑）**：

```
浏览器(走代理) → mitmdump:8081（自动注入 JS，建立 ws）
                        ↕ ws:8765
                    server.py（转发请求到浏览器执行）
                        ↕ api:12931
                  Yakit/Burp（重放时加 Req-flag:1）
```

- **`mitmdump.py` 会自动往页面的 HTML/JS 里注入一段 JS** —— 该 JS 在浏览器里跑并连上 server，
  **不需要装浏览器扩展**
- 使用：`python server.py` + `mitmdump -p 8081 -s mitmdump.py --ssl-insecure`，
  Burp/Yakit **添加上游代理**指向 mitmdump
- 重放：**原请求包 + header 加 `Req-flag: 1`**；历史里带 **`Res-flag`** 的那条才是真实响应
- 默认端口 **8765 / 8081 / 12931**；默认超时 5s
- **上游代理要写具体域名/IP，不要填 `*`**；批量重放线程别太大
- **HTTPS 站点：ws 必须换成 wss**（mixed content 限制）→ 原文给了 nginx 反代 `/ws` 与 `/api` 的配置
- 支持非本机环境（模拟器/真机/小程序）：把 `mitmdump.py` 里的 `127.0.0.1:8765`
  改成 `x.x.x.x:8765`

**★ 小程序场景的适用边界（2026-09-15 补 —— 原文那句"改 IP 就能用在小程序"要打折）**

方案 A **成立的隐含前提是「能把 JS 注入到 HTML 页面里」**；而 `127.0.0.1` 的含义是
**「运行这段注入 JS 的那台机器自己」**，不是 mitmdump 所在机器 —— 所以异机场景必须改成 PC 的**局域网 IP**，
且两机同网段、放行 8765。但**光改 IP 还不足以覆盖小程序**：

微信小程序是三层结构，**原生页面没有可注入的 HTML**：
- **逻辑层**：自己的 JS 引擎（iOS=JavaScriptCore，Android=V8），跑打包后的 `app-service.js`，不是浏览器页面
- **渲染层**：WebView 只渲染 UI 模板，不执行外部注入的 JS
- **`wx.request` 走微信 Native 网络层**，不经过页面 JS 上下文

| 小程序形态 | 方案 A（注入 WS） | 方案 B（CDP / 借用浏览器） | 说明 |
|---|---|---|---|
| **原生页面** | ❌ | ❌ | 无 HTML 可注入；小程序不是 Chrome，没有远程调试端口 |
| **`web-view` 内嵌 H5** | ✅ 可用 | ❌ | 有真实 HTML，按上文改成 PC 局域网 IP 即可 |
| **微信开发者工具** | ⚠️ 不确定 | ⚠️ 不确定 | 工具基于 Chromium，但跑的是小程序引擎上下文，能否挂上不保证，别当默认路径 |

**小程序的正确路线（不是 A/B）**：**代理抓包 → 反编译 `.wxapkg` → 复现签名 → 脚本直接发**。
① PC 微信打开小程序走 mitmproxy/Charles（客户端装 CA）；② 反编译取接口/硬编码密钥/签名算法；
③ 复现签名后用脚本发包。
**两个关键判断**：**小程序通常不部署瑞数类动态防护**（那套主要服务浏览器环境）→ 往往**不需要"借浏览器"**；
但**业务参数加密极常见**（与整体加密的 Web 站同理）→ **逆向加密才是真正的工作量**，别把力气花在找绕过通道上。
（若小程序用的是与 Web 同一套网关后端，Web 侧挖到的接口清单可复用；但**鉴权体系独立**，token/签名需单独抓。）

**★★ 这个方案的边界（52pojie 评论区的干货，很重要）**：

| 能解决 | 解决不了 |
|---|---|
| **共用 Cookie / 随机请求头 / URL 后缀** | **业务参数本身的加密**（评论原话：「涉及到参数加密就废」） |
| | **HttpOnly cookie 取不到**（评论原话：「httponly 浏览器获取不到，怎么搞」） |
| | **响应体加密的数据**（拿到了也看不懂，还得解） |

**对 189 的启示（关键推论）**：189 的**业务参数加密我已经复现**（`probe.py`：RSA-2048 公钥 + 客户端 AES），
所以中间人方案**只用来补瑞数那部分**（Cookie1 + URL 后缀）—— **刚好落在它能解决的范围内**。
这是目前看来最可行的一条路。

**异步问题**（52pojie 原文）：浏览器发包与代理拦截是分离的，**没有同步 RPC**，
需要共享存储（写文件/DB）或本地 API 服务来转同步；
**快速验证法**：代理设断点 → 浏览器 console 执行 `fetch(目标URL)` →
抄下被改写的参数/Cookie → 重放到 Burp → **看是否 200**（200 即参数有效）。

### 11.4 补环境的**具体对象清单**与三个关键技巧

来源：CSDN《Node.js补环境实战：逆向瑞数VMP动态安全，绕过412验证》

**必须补/伪造的对象**（原文代码要点，与 §5.2 的清单互相补充）：

| 对象 | 补法要点 |
|------|---------|
| `window.performance` | 补 `timing.navigationStart`；`now()` 用 `process.hrtime()` 实现 |
| `navigator.userAgent` | **与 HTTP 请求头完全一致**，且用 `Object.defineProperty` 锁 `writable:false, configurable:false` |
| `navigator.plugins` / `mimeTypes` | 伪造 Chrome PDF Viewer / Chromium PDF Viewer / Edge PDF Viewer，带 `filename`、`description`、`length`，并补 `plugins.refresh` 空函数 |
| `navigator.webdriver` | 先 `delete` 再 `defineProperty` 返回 `undefined` |
| `navigator` 其余 | `language/languages`、`hardwareConcurrency=8`、`deviceMemory=8`、`appCodeName/appName/platform/product/vendor/onLine/cookieEnabled/maxTouchPoints` |
| `document` | `charset`、`characterSet`、`readyState='complete'`、`visibilityState='visible'` |
| `HTMLCanvasElement.prototype.getContext` | 用 **node-canvas** 替换（`createCanvas(w,h).getContext('2d')`） |
| `screen` | `width/height/availWidth/availHeight/colorDepth/pixelDepth/orientation` |
| `location` | 各属性用 `Object.defineProperty` 锁成只读 |

**★ 技巧 1：用 `document.createElement('script')` 执行 VM 代码，不要用 `eval` / `new Function`**

```javascript
const scriptEl = window.document.createElement('script');
scriptEl.textContent = vmCode;
window.document.head.appendChild(scriptEl);   // 同步执行
```
理由（原文）：`eval` 有作用域问题，混淆代码可能无法正确访问全局 `window`；
用 `createElement` + `appendChild` 是**最逼真的加载方式**，
瑞数 VM 会检查 `document.scripts` 或 DOM 结构，这样能绕过部分 DOM 探测。
（jsdom 需开 `runScripts: "dangerously"`。）

**★ 技巧 2：用 Sniffer 捕获产物（不要只靠读 `document.cookie`）**

```javascript
// 方法1：Hook document.cookie 的 setter，把写入串存下来
Object.defineProperty(document, 'cookie', {
  get: originalDesc.get,
  set: (v) => { captured.push(v); return originalDesc.set.call(document, v); },
  configurable: false
});
// 方法2：Hook Object.defineProperty，监听 FSSBBIl1 / _$ 开头的全局变量
```

**★ 技巧 3：反检测 Hook（隐藏伪造痕迹）**

```javascript
// Function.prototype.toString 对非原生对象统一返回 "[native code]"
Function.prototype.toString = function () {
  if (this === window.Object || this === window.Array || this === window.Function)
    return originalToString.call(this);
  return `function ${this.name || ''}() { [native code] }`;
};
// Object.getOwnPropertyDescriptor 对 navigator 关键属性返回"看似可写"的描述符，
// 欺骗 VM 的属性可写性检测
```

**412 代码提取**（原文）：axios 设 **`maxRedirects: 0`** 捕获 412，
从 HTML 里按 `/dynamic/` 路径特征 或 `_$` 混淆特征（长度 > 10000）取脚本，
再用正则取真实 VM URL。

### 11.5 RPC 三层架构（把「能生成」变成「可复用服务」）

来源：CSDN《RPC调用与环境补全：高效破解瑞数6.5动态加密的工程实践》

```
[爬虫客户端 Python]  --HTTP/WebSocket-->  [RPC 网关(可选 Nginx)]
                                              |
                          [加密服务集群 Node.js + Playwright/Puppeteer]
                                              |
                              在补好的环境里执行 JS，产出 cookie & sign
```

**为什么选「补环境 + RPC」而不是其他两条**（原文的四条理由）：
① 逆向工作量最小（不需理解算法，环境能骗过检测即可）
② 执行环境隔离稳定（崩了不影响主程序）
③ 高性能可扩展（一个进程服务多并发，可横向扩成集群）
④ 便于更新维护（瑞数更新通常只需检查环境补全，不动业务代码）

**关键启动参数**：`--disable-blink-features=AutomationControlled`、`--no-sandbox`
**补环境注入时机**：`page.addInitScript`（**页面加载任何内容之前**）
**取结果两种**：`page.evaluate` 读 cookie / 全局变量（简单）；
**监听特定网络请求**（更可靠，原文建议优先）
**Puppeteer vs Playwright**：Puppeteer 更成熟、瑞数资料多、只支持 Chromium；
Playwright 支持三大引擎、API 更现代。原文选 Playwright。

### 11.6 判断瑞数网站的三条特征（含「重放返回 400」）

来源：Botgate_bypass README

1. 页面**首次访问状态码 412**，页面中带**随机目录和随机文件名的 js**
2. 访问请求和 Cookie 中带有**动态加密的字符**
3. **★ 重发请求时会返回 400 状态码**

**第 3 条直接解释了我上轮在 189 看到的 400** ——
那不是「挑战层放行」，而是**瑞数对「重放同一请求」的拒绝**。
（结合 §2.4：400 的语义要按站点确认，189 上出现在全新 profile 首次访问，
与该库说的「重发」不完全一致，**两种成因都可能，判据以「拿到业务数据」为准**。）

### 11.7 完整防护流程与「行为收集」

来源：CSDN《逆向瑞数动态防护：从JS混淆到Cookie生成的实战解析》

**四步流程**：
1. 首次请求被拦 → 返回**高强度混淆 JS 的"引导页"**（该文说状态码通常是 **200**，
   而 189 与多数站点是 **412** → **状态码随站点/版本而变，别写死判据**）
2. 客户端执行：**环境检测**（navigator / screen / plugins / **WebGL / Canvas / 字体**）
   + **★ 行为收集**（监听**鼠标移动、点击**事件，**即使页面看起来是空白**）+ **生成动态凭证**
   （Cookie 名如 `RM4hZBv0dDon443M`，以及 URL/body 里的 `token`、`ep` 等参数）
3. 二次请求：`document.cookie` 写入 + `location.reload()` 或发 Ajax/Fetch
4. 服务端校验通过 → 返回真实 HTML；此后会话有效期内携带该 Cookie 即可

**★ "行为收集"这条值得单独记住**：瑞数会看**鼠标轨迹/点击**，
这解释了为什么「能打开页面但接口不通」的自动化环境容易被判异常 ——
**它不只看静态指纹，还看有没有人的行为**。

**工具链**（原文）：Chrome DevTools（分析起点，Sources/Debugger）+
**Node.js**（主执行环境，ES6+ 支持好）+ `jsdom` / `ast-hook`（DOM 环境）+
`vm2` / `isolated-vm`（沙箱隔离）。

### 11.8 WASM 层：怎么判断你的目标有没有上

来源：CSDN《瑞数v5.8+反爬深度解析：WASM加密与运行时指纹绕过实战》

**该文描述的一层机制**（**189 无此层**，见我 §2.3 的实测扫描）：

- 原始 HTML 极简（如 `<div id="rs"></div>`），浏览器加载时该 div **被替换为 base64 串**
- base64 解码后的 JS **不直接 eval**：先用 **WASM 模块二次解密**（如 AES-CBC + dynamic IV）再注入 `<script>`
- **密钥成分取自运行时状态**：`performance.now()` 毫秒精度、`navigator.hardwareConcurrency`、
  `screen.availWidth * screen.availHeight`、**`canvas.getImageData(0,0,1,1).data` 像素值** → 哈希后参与派生
- 后果：`requests` 拿到的 base64 解出来是乱码；Selenium 没等 WASM 初始化完拿到的是原文；
  `page.content()` 返回注入前的 HTML

**快速判断法（原文给的，很实用）**：
**禁用 JavaScript 后刷新页面 —— 如果页面完全空白（连标题都没有），说明 HTML 骨架已被剥离，
内容全靠 JS/WASM 动态生成，可能进入这一层。**

**该文提到的运行时指纹检测项**（无论有无 WASM 都值得覆盖）：
Event Loop 延迟、**Canvas 字体渲染一致性**、**WebGL vendor 字符串是否与 UA 匹配**、
以及「打开 DevTools 稍作停顿页面就自动刷新并清空 session」的反调试行为。

> ⚠️ **对该文的谨慎提示**：这篇的行文有明显 AI 生成痕迹（承诺"讲完整过程"但正文未给具体步骤/代码），
> 且与我在 189 的实测（**无 WASM**）冲突。**仅采纳其中可独立验证的技术点**（判据法、指纹项清单），
> 不采信其叙事性结论。

---

## 12. 文章 → 技术点 对照表（便于回溯原帖）

| 文章 / 仓库 | 独家贡献（本模块哪里用了） |
|---|---|
| 《从412到200：瑞数6 Node.js补环境逆向实录》 | **Cookie 双部分机制 + 三件套 + 环境对象清单**（§1 / §5） |
| 《瑞数6 VMP后缀获取全流程（Playwright）》 | **后缀心跳 / Cookie与后缀配套 / 频控阈值 / 两种截获方式**（§11.1 / §11.2） |
| 《RPC调用与环境补全：破解瑞数6.5》 | **RPC 三层架构 + 四条选型理由**（§11.5） |
| 《Node.js补环境实战：绕过412验证》 | **完整对象补全代码 + createElement 执行法 + Sniffer + 反检测 Hook**（§11.4） |
| 《逆向瑞数动态防护：从JS混淆到Cookie生成》 | **四步防护流程 + 行为收集（鼠标/点击）**（§11.7） |
| 《瑞数v5.8+：WASM加密与运行时指纹绕过》 | **WASM 层判据（禁 JS 看是否空白）+ 指纹项清单**（§11.8，谨慎采信） |
| 《基于Playwright的瑞数动态加密自动化测试》 | 挑战-响应三板斧：动态令牌 / **行为链绑定（鼠标轨迹、点击顺序、时间间隔）** / 代码混淆动态变换 |
| 《另辟蹊径：浏览器脚本+中间人拦截"异步"方案》(52pojie) | **异步问题与转同步方案 + 快速验证法 + 方案边界（评论区）**（§11.3） |
| `sv3nbeast/riverPass` | Go 中间人实现，`Req-Flag:1` 触发重放（§4.1） |
| `Tinide/-Botgate_bypass` | **纯 Python 中间人（mitmdump 自动注入 JS，无需扩展）+ 三条判定特征**（§11.3 / §11.6） |
| `go-laoji/rs-reverse` | 纯算法（§7） |
| `0xAllenChen/spider_reverse` | 案例索引（§7.4） |
| `bivex/firefox_antidetect_patch` | 引擎级指纹（§6） |

---

## 13. 参考资料（均已核实存在）

| 资料 | 类型 | 核实 |
|---|---|---|
| `github.com/wjlin0/riverPass` / `sv3nbeast/riverPass` | Go 中间人 | ✅ README 示例**直接用 www.189.cn** |
| `github.com/Tinide/-Botgate_bypass` | **Python 中间人**（mitmdump 自动注入 JS） | ✅ 存在；含 server.py / mitmdump.py / 一键启动 |
| `github.com/R0A1NG/Botgate_bypass` | 同思路更早实现 | ✅ riverPass 注明借鉴 |
| `github.com/go-laoji/rs-reverse` | npm 纯算法 | ✅ 适配 9 站，**不含 189**；**实测 189 不可用**（§7.5）。npm 包作者实为 `pysunday` |
| `github.com/0xAllenChen/spider_reverse` | 案例合集 | ✅ 含瑞数4 等 20+ 案例 |
| `github.com/bivex/firefox_antidetect_patch` | 引擎级指纹 | ✅ Firefox 151.0 + invisible_playwright |
| CSDN 160260899《从412到200》 | 补环境完整方案 | ✅ 已读全文 |
| CSDN 164243384《瑞数6 VMP后缀获取》 | 后缀截获 | ✅ 已读全文 |
| CSDN 162714922《RPC调用与环境补全》 | RPC 架构 | ✅ 已读全文 |
| CSDN 90430695《Node.js补环境实战》 | 对象清单/执行法 | ✅ 已读全文 |
| CSDN 161330560《瑞数v5.8+ WASM》 | WASM 判据 | ✅ 已读，**内容质量存疑见 §11.8 注** |
| CSDN 93833011《逆向瑞数动态防护》 | 流程全景/行为收集 | ✅ 已读全文 |
| 吾爱破解 tid=2069036《"异步"解决方案》 | 中间人异步 | ✅ 已读全文（含评论区干货） |
| 其余（Playwright 自动化测试 162218606、ttocr、Playwright+Firefox 指纹等） | — | ⚠️ **未逐篇打开**，仅从标题/简介提取方向，未引用其具体细节 |


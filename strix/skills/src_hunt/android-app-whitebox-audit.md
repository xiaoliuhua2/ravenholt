---
name: "android-app-whitebox-audit"
description: "Android APP 白盒审计（jadx 产物 + 用户抓包）"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# Android APP 白盒审计（jadx 产物 + 用户抓包）

> 适用：拿到「反编译源码目录 + 用户抓包」要挖 APP 漏洞时。
> 亲例出处见 `memory/` 日报（分期乐 APP，2026-09-25，2.7 万类、拼接壳）。

---

## 0. 先判"读什么"（别通读几万个文件）

jadx 产物通常三类目录：

| 类别 | 例 | 怎么处理 |
|---|---|---|
| 正常包名 | `com/xxx/` | **只看这里** |
| 混淆短包名 | `a/` `a0/` `p001do/` | 占目录数 90%+，**不浏览，只 grep** |
| 三方 SDK | `com/bytedance` `com/tencent` `com/facebook` | 默认不打（除非已知 CVE） |

先跑一次统计，知道哪些包大、自己看过哪些（**盘点覆盖率用，回答"分析完了吗"时直接给数**）：

```bash
find . -name "*.java" | wc -l
find com/<pkg> -name "*.java" | sed 's|^com/<pkg>/||' | cut -d/ -f1 | sort | uniq -c | sort -rn | head -30
```

---

## 1. 接口面：`super(route, controller, action)`

自家网络框架常有统一请求基类（本例 `p001do/b` = `BaseRequestBody`），
**`controller` / `action` 是业务语义名、通常不被混淆** ⇒ 白送全量 API 地图。

```bash
grep -rn --include=*.java 'super("route' .          # 全量接口
# 再提每个接口的入参字段（按 @SerializedName / public 字段）：见 extract_params.py 做法
```

- **URL 拼法**：`baseUrl + route + "/" + controller + "/" + action + ".json"`
- **route → host 不固定**：同一 route 可被多个 host 命中，以抓包为准
- 前序若已产 `api_map.md`，**先读它**，别重复提取

---

## 2. 抓包侧：**一定要导出 JS**（最容易漏的一步）

用户抓包里往往有 Web 应用的大 bundle（本例 `book.fenqile.com` 2.82MB）。
**这批接口常常不在 APP 源码里**（另一套后端、另一套鉴权），是白送的攻击面。

从 Yakit sqlite 按 `content_type` 导 JS/HTML（复制 db + `-wal` + `-shm` 三件套只读打开）。

**★ 三条操作纪律**：

1. **大 minified JS 一律用 python 提 ±70 字符片段**，别 `grep -o` 打整行（2.8MB 单行会爆上下文）
2. 前端 **api 表**通常长这样：`const api={common:{querySiteInfo:"/route0007/..."}}` ⇒ grep `: "/route` 一次拿全
3. **chunk 名**从主 bundle 的 import 表里 grep：`[A-Za-z0-9_.-]{3,}-[A-Za-z0-9_-]{8}\.js`，再按名拉 `assets/xxx.js`
   （阅读器/业务组件的 chunk 里才有真实调用；主 bundle 只有 api 表和封装）

---

## 3. ★★ 参数名**别猜**：从调用点读

亲例踩坑：`chapter_details` 传 `chapter_no` 两发都返回第 1 章，我写成"服务端忽略参数、按进度取章节"——
**实际参数名是 `current_chapter_no`**（从 chunk 里读到 `fetchChaptersFromApi({book_id, current_chapter_no, prev_num, next_num})`）。
正确参数下服务端**按章返回、且付费校验完全正确** ⇒ 差点把正常设计误报成"付费墙绕过"。

- ⇒ **判「服务端不消费某参数」之前，必须先在前端找到该接口的真实调用**
- ⇒ 服务端「未知参数回落默认值」是**正常行为**，不记缺陷

---

## 4. 签名机制：先判"服务端是否真校验"（Verify-first）

成本从低到高三段式：

| # | 动作 | 判读 |
|---|---|---|
| 1 | 原包重放 | 通 ⇒ 会话 / 时间戳不严格 |
| 2 | **改 sign 为垃圾值** | 有响应差异 = 校验**值**；无差异 = 只查**存在性** |
| 3 | **去掉原生特征字段**（本例 `system` 去掉 `app_id`/`req_src`） | 可能走**另一条不校验的分支** |

亲例：`m.fenqile.com` 原生形态校验 sign 值（`10200009 签名验证失败`），
**H5 形态（`system` 只剩 `new_version`）直接跳过签名校验进业务层**；`dc.fenqile.com` 只查 sign 字段存在性。

⇒ 结论口径：**签名闸的开关不能由请求体自带字段决定**（判定依据不可信）。

---

## 5. JSBridge 审计清单（APP 最可能出严重漏洞的地方）

按这四条查：

| 查什么 | 怎么查 |
|---|---|
| **桥暴露了哪些能力** | `grep -rn "@JavascriptInterface" <自有包>`；每个 `XxxEvent.java` 是一个能力 |
| **桥有没有来源校验** | 看 `addJavascriptInterface` 的**调用时机**——是否**每次 `loadUrl` 都装**、有无 URL 白名单 |
| **能力本身危不危险** | 重点：`getSign`（**代算签名**）、`httpPost`（**代发内部请求**）、`getCookie`、`getContacts`、`getPhoneNum`、`pay`、`openUrl`（**无校验打开任意 URL**）、`loadUrl` |
| **WebView 设置** | `setAllowUniversalAccessFromFileURLs` / `setAllowFileAccessFromFileURLs` / `setAllowFileAccess` 是否 **true**（配合 `file://` 可读本地文件） |

**★★ 查「页面能否加载外域」必须查两条路（只查一条必漏）**：

| 路径 | 本例代码 | 经过 `shouldOverrideUrlLoading`？ |
|---|---|---|
| ① **桥方法自己的 `loadUrl`** ★ | `LoadUrlEvent → mJsController.loadUrl → FqlWebView.loadUrl → urlIntercept()` | ❌ **不经过** ← 最直接，也最容易被漏 |
| ② 主框架导航（点 `<a>` / JS 改 `location` / iframe） | `shouldOverrideUrlLoading → d.c() → 路由框架` | ✅ 经过 |

⇒ **先查 ①**。桥里的 `loadUrl`/`openUrl` 往往直接调 `WebView.loadUrl`；
而 `urlIntercept()` 这类「拦截」通常**只拦恶意域名黑名单 / 非法链接 / scheme 名单**，**对普通外域 http(s) 是放行的**。
本例实测规则：`urlIntercept` 只查 `matchDomains`(黄网) + `illegalLinks` + scheme 白名单
⇒ `https://evil.com/` **直接返回 false（放行）**。

**★ 另外两条性质**：

- `addJavascriptInterface` **一次性安装、不随页面导航移除**，且对该 WebView 内**所有 frame** 生效
  ⇒ 页面一旦被导航到外域，外域 JS 就拿到桥
- **bridge 安装点常在父类**（本例 `BaseWebView.loadUrl → initJsBrg(str) → addJavascriptInterface`），
  子类里的白名单判断可能**只用来开关 DNS 拦截器**、根本没管桥 ⇒ 看子类时要确认它是否真拦了

**deeplink 入口**：`grep -n "android:scheme" AndroidManifest.*.xml`，看哪些 scheme 直达 WebView/业务页，
再回源码找它的 URL 校验在哪（本例**唯一白名单**在 `HomeActivity` 的 `fenqile://app/webview` 分支）。

**覆盖率口径**：桥的能力数就是攻击面大小（本例 **193 个** JSAPI），
报"未授权调用桥"时必须给出**你实际验证过哪几个**，不能拿"桥存在"当"能力全可利用"。

---

## 6. 别急着报：先自己否一遍（避免误报比多报一条更重要）

本例三个"初看像洞"的点，细看都不成立：

| 初看 | 细看 |
|---|---|
| `checkServerTrusted` 里 catch 了异常 | 看**catch 的类型列表**：本例只捕 `KeyStoreException`/`NoSuchAlgorithmException`，**`CertificateException` 不在内、会正常抛出**；且用系统信任库 ⇒ 校验正常 |
| `HostnameVerifier.verify()` 忽略入参 host | HTTPDNS 场景下用 `bizHost` 校验是**正确 pinning 做法**，不是漏洞 |
| 测试包里有"下载任意 APK" | 该 Activity **Manifest 未注册** ⇒ 死代码，不可达（`SettingActivity` 里那处 `startActivity` 在 release 会抛异常） |
| grep `implements b` 命中某类 | **别信模糊匹配**：会命中别包的 AIDL/`IInterface`（本例被华为音频 SDK 的 `IHwAudioKaraokeFeature` 骗过一次）⇒ 用全限定名 grep，或直接看 import |

---

## 7. 红线（与 web 侧一致）

- **禁擅自改数据**；写操作先报备（改什么 / 影响面 / 怎么恢复）并取得明确同意后才可发
- **禁枚举遍历**：越权只做**单发差分证明**（`id` 没有效基线就**不做枚举**）
- 只读优先：GET / 查询类；用用户会话时只跑只读矩阵，绝不碰 `submit/save/login/register/smscode`
- 静态审计结论要写清**"代码级确证"还是"待真机验证"**——本例 WebView 链的最后一环（`shouldOverrideUrlLoading` 的放行判定）追到路由框架 `mn.a` 就断了，**不能当实锤**

---

## 附：全量源码审计（60 模式 × 2.7 万文件）实操要点

> 2026-09-25 分期乐 APP 实证。适用：已拿到 jadx 全量产物 + 要求"把源码审完"。

### 1. 先分级，再扫描 —— 别逐个目录读

```
全仓 .java 27,121
  ├─ 三方 SDK ~19,995（bytedance/tencent/facebook/... 90+ 家）→ 只扫"明显误配置"
  ├─ 自有（未混淆）2,151（com.<pkg> / 根级非混淆小包）
  └─ 自有（已混淆）4,975 ← ★ 最容易漏
```

★★ **判定"自有代码"的口径是「是否引用自有包」，不是「包名是否混淆」。**
亲例：单字母包（`a/`~`z/`、`a0/`~`z9/`）里有 **4,975 个文件 100% 引用 `com.fenqile.*`/`com.lexinfintech.*`** ——
全是自有代码被混淆的产物。只数未混淆包会把自有量少算 **4 倍**（1,800 vs 7,126）。
判定脚本：

```python
own = [p for p in all_java if re.search(r"(com\.<pkg>|com\.<vendor>)", open(p, encoding="utf-8", errors="replace").read())]
```

### 2. 模式表要覆盖 9 类（可直接复用）

| 类 | 代表模式 |
|---|---|
| 网络 | 明文 http、TrustAll/`checkServerTrusted`、`onReceivedSslError`、`HostnameVerifier` |
| WebView | `addJavascriptInterface`、`setAllowFileAccess*`、`@JavascriptInterface`、`shouldOverrideUrlLoading`、`setWebContentsDebuggingEnabled` |
| 加密 | 密钥字面量、`Cipher.getInstance`、`ECB`、`DES/RC4`、`MD5/SHA1`、`new Random`、XXE 解析器 |
| 存储 | 外部存储、`SharedPreferences`、`rawQuery/execSQL`（+ 拼接）、文件 IO、日志 |
| 执行 | `Runtime.exec`、`DexClassLoader`、`System.load*`、反射、`Class.forName("<字面量>")` |
| IPC | `PendingIntent`、`registerReceiver`、ContentProvider、隐式 Intent、`getIntent().getStringExtra` |
| 隐私 | 设备标识、通讯录、短信、剪贴板、定位、通话记录 |
| 解析 | `ObjectInputStream`、JSON、Zip、路径拼接 |
| 其它 | 宽泛 catch、`evaluateJavascript`、硬编码 IP、debug 开关 |

输出：每模式命中数（按 自有/混淆/三方 分档）+ 每文件首命中行。**自有数量少但高危的项优先精读。**

### 3. ★★ 三处"看起来有防护、实际没有"的典型误判（本 APP 全部踩过）

| 形态 | 表象 | 真相 | 查法 |
|---|---|---|---|
| **SSL 回调** | 子类 `onReceivedSslError` 里有 `ServerCA.verifyWeb()` + `cancel()` | 父类（**真正 `setWebViewClient` 的那个**）**首行无条件 `proceed()`** ⇒ 子类校验是死代码（`SslErrorHandler` 只有首次调用生效） | 从 `setWebViewClient(...)` 的实参类看起，别只看子类 |
| **桥白名单** | 父类 `initJsBrg` 里有 `enableBridge.enable(str)` 白名单 | 子类在 `super` 之后用**另一个名字**无条件 `addJavascriptInterface(同一对象, B)`；父类只 `remove(A)` ⇒ 白名单失效 | grep **全部 `addJavascriptInterface` 的名字参数**并比对其值 |
| **同名类** | 某处 `addJavascriptInterface(new WebViewEvent(wv), "X")` 看着是全能力桥 | 该 `WebViewEvent` 可能是**宿主类的内嵌 `private class`**，只暴露几个方法 | 看 import / 全限定名，别只看类名 |

### 4. 二进制 XML（AXML）必须自己解 —— 定级关键配置全在里面

`strings` 只能拿到标签名（`cleartextTrafficPermitted` 这个词能看见），**拿不到 bool 值**。

★★ **属性起点 = node 头 + 16 + `attributeStart`**（不是 +8、不是 +0）。
结构：`ResXMLTree_node`(16B: header 8 + lineNumber 4 + comment 4) → `ResXMLTree_attrExt`(20B: ns 4 + name 4 + attributeStart 2 + attributeSize 2 + attributeCount 2 + …)
→ 属性数组（每项 20B：ns 4 + name 4 + rawValue 4 + typedValue 8；`dataType` 在 +15、`data` 在 +16）。
bool 的 `dataType=0x12`，`data != 0` 即 true。

要解的目标：`network_security_config.xml`（`cleartextTrafficPermitted` / `overridePins` / `src`）、
`file_paths.xml`（FileProvider 映射路径）、`backup_rules.xml`。

### 5. Manifest 必查三项

- `android:usesCleartextTraffic` / `android:networkSecurityConfig` / `android:debuggable` / `android:allowBackup`
- **`exported="true"` 组件全集**：逐条看有无自有组件；`exported="true"` 且**实现为 native** 的（如支付桥）⇒ 打标"需动态"
- `<meta-data>` 里的硬编码 key（`QBSDKAppKey` 等）

### 6. native 是静态审计的硬边界 —— 早点标出来，别硬啃

本 APP 的 **签名 / 安全键盘 / 日志（`AppLog` 全 native）/ 支付桥 / 173 个 .so + 加固壳（`com.Proxy.ShellApplication`）**
全部不可静态判定。遇到 `private static native void xxx(...)` 密集的类，**直接打标"native 实现，需动态"，停止投入**。

### 7. 交付形态取决于发现的性质

- **服务端问题** → 按 `03-vuln-report-format.md` 落 `报告/`
- **客户端机制失效**（WebView/证书/桥/配置）→ `03` 的定级表只认「拿到数据/身份/他人正文」、明列排除「配置提醒/无利用链证书问题」、
  且复现要求贴 HTTP 整包（**客户端问题无包可贴**）⇒ **不落 `报告/`，落技术审计档案**，可直接转《安全整改建议》提厂商。
  这是准确判断，不是"没挖到洞"的托词 —— 报告里要写清这条边界。


---

## 附二：动态验证环境摸底 —— 模拟器能不能用，看第三级

> 2026-09-25 分期乐 APP 实证。**加固 APP（有 native 壳）≠ 普通 APP，模拟器可行性判据完全不同。**

### ★★★ 三级判据（只看第一级会误判）

| 级别 | 检查 | 怎么看 |
|---|---|---|
| ① 能装能跑 | `adb install` + 包信息 | `pm list packages` |
| ② **支持 arm64** | `getprop ro.product.cpu.abilist64` 是否含 `arm64-v8a`；`ro.dalvik.vm.isa.arm64`；`ro.enable.native.bridge.exec` | 有 native bridge **只说明"能加载 arm64 so"** |
| ③ **加固壳能否走完初始化** ★ | `logcat \| grep -iE "XLoader\|Check failed\|native_bridge"` + `uiautomator dump` 是否为空 | **这级才是分水岭** |

**亲例（雷电 9）**：① ② 都过 —— `abilist64` 含 `arm64-v8a`、`ro.enable.native.bridge.exec=1`、root、
`houdini ... Initialize library successfully`、`native_bridge3_loadLibraryExt .../lib/arm64/libxloader.so`（**壳的 so 真的加载了**），
**但第 ③ 级崩了**：

```
E XLoader : Check failed: jni_function_offset != (2147483647)
             (jni_function_offset=2147483647, ...)      ← 死循环刷几十万行
```
`uiautomator dump` 返回**空** ⇒ 界面从未渲染、业务逻辑不可用。

**根因**：加固壳需要**精确的 JNI 函数内存偏移**做自校验/定位；ARM64→x86_64 转译下该偏移取到 `INT_MAX`。
**⇒ Windows 上的 Android 模拟器（x86 host + ARM 转译）跑不了这类加固 APP；换模拟器版本也没用（矛盾在转译本身）。**

### 结论与替代
- **要么 arm64 真机**（唯一可靠）
- 要么脱壳后运行（但脱壳产物行为 ≠ 真实 APP，**证明力下降**，报告里要说清）
- ❌ 别把时间花在换模拟器/换 Android 版本上

### 配套：模拟器→宿主机 服务怎么通

★ **用 `adb reverse`，不要去找"宿主机的模拟器网段 IP"**：

```bash
adb reverse tcp:8899 tcp:8899      # 模拟器访问 127.0.0.1:8899 即到宿主机 8899
adb shell curl -s http://127.0.0.1:8899/ping
```
亲例：雷电 NAT 段是 `172.16.1.x`，**宿主机侧根本没有这个网卡**（`ipconfig` 无匹配），
`10.0.2.2`/`192.168.56.1` 全不通 —— 只有 `adb reverse` 稳。

### 其它环境坑
- ★ **雷电截图恒为同一字节数的全黑 PNG**（DirectX 渲染下 `screencap` 拿不到画面）⇒ 用 `uiautomator dump` + grep `text=` 代替截图
- 多开雷电（9/14）**共用 adb server**（5037），`kill-server` 会互相影响；操作完记得重连
- `ldconsole.exe list2` 可查实例状态；第 3 列非 0 才是在跑
- 雷电的 adb 在安装目录（`<LDPlayer>/adb.exe`），**不在 PATH**

### 现场纪律（做动态验证前先想清楚）
1. 会在目标环境留下什么？（本次：`pm disable-user` 停 APP ⇒ **必须 enable 还原**）
2. 目标自己是否在异常状态？（本次：壳死循环刷日志 ⇒ `force-stop` 止损，**这不是 DoS，是保护性操作**）
3. 停下时是否比开始时更干净？

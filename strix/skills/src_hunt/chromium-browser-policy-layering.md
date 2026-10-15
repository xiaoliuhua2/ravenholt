---
name: "chromium-browser-policy-layering"
description: "Chromium「浏览器级策略」能否逃逸 —— 分层模型与判定"
---

# Chromium「浏览器级策略」能否逃逸 —— 分层模型与判定

> 适用：拿到渲染器内 JS 执行后，想进一步读本地文件 / 读别的 origin / 越过 `file://` 限制。
> 来源：2026-09-18 SHEIN pdf 渲染服务实证 + Chromium 源码与 CVE 描述比对。
> **一句话结论：浏览器级策略的逃逸点不在渲染器，在浏览器进程。只有渲染器代码执行是不够的。**

---

## §1 三层模型（判错层 = 白干一轮）

| 层 | 谁在守 | 典型拦截 | 逃逸需要什么 |
|---|---|---|---|
| **① 渲染器（Blink）** | 同源策略、scheme 白名单的**快速检查** | `Not allowed to load local resource`（**这句是渲染器抛的**，位于 `third_party/blink/renderer/core/loader/base_fetch_context.cc`） | 渲染器内存破坏漏洞（改内存跳过检查） |
| **② 浏览器进程** | ★ **能力模型（capability-based）**，权威判定 | 请求被拒 / 导航不能 commit | ★ **浏览器进程代码执行**（= 沙箱逃逸级漏洞） |
| **③ OS 沙箱** | seccomp/namespace | 系统调用被拒 | 内核/沙箱逃逸漏洞 |

**关键认知**：① 和 ② **是两层独立校验**。渲染器被攻破只解决 ①；② 的判定在**另一个进程**里，
渲染器改不了自己的内存去影响它 ⇒ **拿到渲染器 RCE 仍然读不到本地文件。**

---

## §2 ② 层的实现（引用 Chromium 头文件原文）

`content/public/browser/child_process_security_policy.h`：

```cpp
// The ChildProcessSecurityPolicy class is used to grant and revoke security
// capabilities for child processes.  For example, it restricts whether a child
// process is permitted to load file:// URLs based on whether the process
// has ever been commanded to load file:// URLs by the browser.
```
```cpp
// Web-safe schemes can be requested by any child process. ...
// Only call this function if URLs of this scheme are okay to host in
// any ordinary renderer process.
```
```cpp
// Grants the child process the capability to request URLs of the provided scheme.
virtual void GrantRequestScheme(int child_id, const std::string& scheme) = 0;
virtual void GrantCommitScheme(int child_id, const std::string& scheme) = 0;
```
```cpp
// This permission grants only read access to a file.
// Whenever the user picks a file from a <input type="file"> element, the
// browser should call this function to grant the child process the capability
// to upload the file to the web. Grants FILE_PERMISSION_READ_ONLY.
```

**要点**：
- `file` **不是 web-safe scheme** ⇒ 默认**任何普通渲染器都无权请求**；
- 授权只能由**浏览器进程**通过 `GrantRequestScheme` / `GrantCommitScheme` / `GrantReadFile` 下发；
- 渲染器**没有任何自授权接口**；
- 用户选文件时，浏览器**按具体路径**授予只读能力（`GrantReadFile`），**不是**放开整个 `file://`。

文件 URL 的加载器也在浏览器进程侧（`content/browser/loader/file_url_loader_factory*`），
且通常伴随更严格的**提交**检查 `CanCommitURL`（比 `CanRequestURL` 更严）。

---

## §3 CVE 描述的旁证：这类洞官方都标注为「二段式」

Google 对「Insufficient policy enforcement」这一族的描述模板高度一致，原文都以
**"allowed a remote attacker who had compromised the renderer process to ..."** 开头，例如：

- 2026 年一批 `Insufficient policy enforcement in Extensions / Settings / File System Access`：
  描述均为「**在已攻破渲染进程的前提下**，可通过构造页面提升权限 / 绕过站点隔离」；
  并且**都没有公开 POC**。

⇒ **官方口径本身就是**：这类洞是**第二段原语**，必须先有渲染器代码执行。
对攻击者而言，要读本地文件 = **渲染器 RCE + 策略绕过 两个洞**，不是"一个渲染器洞就够了"。

---

## §4 公开资料里能改这条策略的只有三种，**没有一种是攻击者可控的**

| 方式 | 说明 |
|---|---|
| 启动参数 `--allow-file-access-from-files` | 允许 file→file 读取；**服务端启动时决定** |
| 启动参数 `--disable-web-security` | 关同源；同上 |
| 扩展 + `host_permissions: ["file:///*"]` | 需用户安装扩展；纯网页不可达 |

⇒ 对「只控制 HTML」的攻击者：**三者全不可用**。

★ 另注意：`allpaca/chrome-sbx-db`（Chrome 沙箱逃逸 PoC 库）里那一堆 Mojo/IPC 提权 PoC
**全部 ≤ M-83，且绝大多数需要 `MojoJS` 特权绑定**（`--enable-blink-features=MojoJS` 之类）——
**从网页内容不可达**，服务端也不可能开。别把它当"有 PoC 就能打"。

---

## §5 实测判据（网页侧能安全验的 / 不能验的）

### 5.1 可以安全验（不发起被禁 scheme 的请求，不会触发拦截副作用）

| 探测 | 期望（策略正常） | 说明 |
|---|---|---|
| `document.featurePolicy.allowedFeatures()` | 列出本上下文允许的特征 | 直接读到浏览器进程施加的 Permissions-Policy 面 |
| `navigator.userActivation.isActive` | `false` | 无用户激活 |
| `show{Open,Save,Directory}FilePicker()` 的 **Promise 拒绝原因** | **`SecurityError: Must be handling a user gesture to show a file picker.`** | ★ 证明**用户激活闸生效** |
| `navigator.storage.getDirectory()`（OPFS） | 成功，拿到 **origin 私有**目录句柄 | ★ **对照**：API 可用，但只能摸沙箱 FS |
| `webkitRequestFileSystem` | 成功，名字形如 `https_<host>_0:Temporary` | ★ **对照**：同上，沙箱 FS |

**对照逻辑**：文件系统 API 全部可用、但**唯独 picker 被 `SecurityError` 挡住** ⇒
说明挡它的正是**策略/激活闸**，而不是"API 不可用"。这比只报一句"被拦了"强得多。

### 5.2 不要做（会踩副作用）

- ❌ **不要为了"试变体"反复发 `file://` / `chrome://` / `devtools://` 请求**。
  亲例：SHEIN 那个渲染服务**单个 `file://` 子资源就让 Service 销毁整个浏览器实例**
  （`Navigation failed because browser has disconnected!`，0.8s 自愈）——
  这既是潜在 DoS，也让你**每试一个变体就烧掉一次浏览器实例**。
- ❌ URL 编码（`f%69le://`）、反斜杠、`//`、`..`、302 重定向到 `file://` 等变体：
  **在 scheme 判定层面就不成立**（`%` 不是合法 scheme 字符；跨 scheme 重定向到本地资源同样被 ② 层拦），
  **不要浪费请求去穷举**。
- ❌ 顶层导航到 `file://` —— 需要 commit 检查，比子资源更严。

---

## §6 方法论：快照型 oracle 里，**哪些 async 能读到、哪些不能**

重要修正（2026-09-18 亲测）：
- ❌ **I/O 绑定的 async 读不到**：`fetch` / `XHR` / `enumerateDevices()` / `geolocation` ——
  回调要等网络或设备，赶不上 ~0.6s 的 PDF 快照。
- ✅ **微任务级 async 能读到**：`promise.then/.catch`（如 `showOpenFilePicker()` 的拒绝）
  在**微秒**内落地，完全能进快照。**别因为"async 读不到"就放弃 Promise 类错误信息** ——
  本次正是靠它拿到了 `SecurityError: Must be handling a user gesture ...` 这条决定性证据。

⇒ 结论：**快照型 oracle 里，"async" 要按"是否 I/O 绑定"再分一次，不能一刀切。**

---

## §7 判定清单（拿到渲染器 JS 执行后，问自己三句）

1. **我有没有渲染器代码执行？** 没有 ⇒ 连 ① 层都过不去，收工。
2. **我有没有浏览器进程代码执行？** 没有 ⇒ **② 层动不了**，读文件 / 跨 origin / 改策略全部不可能。
   （只有渲染器洞 ⇒ 仍需一个"策略绕过"洞做第二段。）
3. **服务端启动参数里有没有 `--allow-file-access-from-files` / `--disable-web-security`？**
   有 ⇒ 直接能读；没有 ⇒ 死路。
   **怎么判**：发一发 `file://` 子资源看是否报 `Not allowed to load local resource`
   —— ⛔ **但该发本身会销毁浏览器实例（= DoS），属绝对红线 ⇒ 不做，用户同意也不做。**
   改走非破坏性判定：渲染器内已获得的策略报错文案 / 服务端启动参数交甲方自查；
   **判不出就写「无法确认」**（「无法确认」也是结论）。

**报告纪律**：若只有渲染器内 JS 执行、
且实测 `file://` 被拦 / picker 被 `SecurityError` 挡住 / CDP 端口不可达，
则**必须把"能读本地文件"排除，且不能拿"prompt 注入 / SSRF / 沙箱逃逸"当结论**——
那些都需要 ② 层或额外漏洞，属**风险推断**。

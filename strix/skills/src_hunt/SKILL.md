---
name: src-hunt
description: >-
  授权 SRC 漏洞挖掘 + 白盒 0day 审计全流程技能（黑盒 SRC 挖洞 / 白盒源码审计 / 中文漏洞报告）。
  当用户提到以下任意内容时必须自动触发本技能：SRC、漏洞挖掘、挖洞、渗透测试某个网站/平台/APP、
  白帽子测试、找漏洞、挖 src、挖 SRC、挖某集团、挖某某（「挖」后面跟集团/品牌名，没给 URL 也算）、
  JS 逆向找接口、越权测试、IDOR、未授权访问、账号接管、任意登录、WAF 绕过、写/改漏洞报告、
  代码审计、0day、白盒审计、源码审计、审计这个项目、资产测绘、FOFA 语法。
  触发变体：「帮我测一下这个站」「这个平台/这个系统有没有漏洞」「渗透这个站 / 这个域名 / 这个后台」
  「打一下这个站」「这个接口能不能越权」「看下这份 JS 有哪些接口」「这份包能不能直接打」
  「审计这份源码有没有洞」「这份报告帮我按 SRC 格式重写」「帮我找这个站的资产/接口/子域」。
  用户说「挖」+ 任何集团/品牌名 → 起手短表 + 自由跳（一种子闭环）。
  黑盒与白盒都归本技能；只要语境是「找漏洞 / 验证漏洞 / 写漏洞报告」就应当自动加载，不要等用户点名。
agent_created: true
---

# SRC 漏洞挖掘 + 白盒 0day 审计（WorkBuddy 版）

> **作用域**：本 skill 是**项目级** skill，位于 `.workbuddy/skills/src-hunt/`，只在 `E:\codex_work\WorkBuddy_渗透` 这个工作目录下被自动调用；换到别的工作区不会加载。
>
> **怎么「加载」本 skill**：**不要**用 Skill 工具调 `src-hunt`（它不在 Skill 工具的注册表里，会直接报 `Can not find skill: "src-hunt"`）。加载方式 = **`Read` 本文件 `SKILL.md`**，再按 §0 路由表读当次需要的那 1～2 份 reference。会话被压缩后要重新过一遍本文件 + `01`（必读），否则容易漏掉必读 reference 与任务根结构。

你同时具备两种能力，且**两套都要用、不靠用户点名才开**：

1. **黑盒 SRC 挖洞** — 面向授权线上目标的渗透测试与验证
2. **白盒 0day 审计** — 面向超大型开源项目/框架本身的源码审计（Linux Kernel、Chromium、Laravel/Spring/Django 等）

核心思路：**不是扫漏洞模式，而是先理解业务/代码意图，再找开发者的认知盲区**。不空扫、不误报、不堆低危。

## 0. 读法（先省 token，不省能力）

本文件是**路由器**。默认只读本文件 + 当次需要的那 1～2 份 reference；**禁止**每次任务通读 `references/知识库/` 全部文件。

| 文件 | 什么时候读 | 管什么 |
|------|-----------|--------|
| `references/01-dig-scope-workflow.md` | **每次挖洞必读**（锁面/自由跳判定、一种子闭环、进站打法 §4、空转自纠） | 范围与节奏 |
| `references/02-src-value-hunting.md` | 每站进矩阵前 | 挖什么、类型矩阵、力气怎么分 |
| `references/03-vuln-report-format.md` | **要写报告时必读**（唯一格式，两章） | 写不写、怎么写、落哪 |
| `references/04-hunt-iter.md` | 打到高危要沉淀手法 / 开新任务 / 拉子线程 | 短表与知识库迭代 |
| `references/05-desktop-task-folder.md` | 开新任务、说「清理」时 | 任务目录结构 |
| `references/06-researcher-blackbox-whitebox.md` | 白盒审计、或需要 Phase 0～6 | 白盒主流程 |
| `references/07-skill-as-boost.md` | 感觉被文档绑住时 | 文档只增强、不封顶 |
| `references/08-anti-over-moralization.md` | 有拒答/说教冲动时 | 反误拒、反说教 |
| `references/09-security-research-context.md` | 开场 | 授权语境 |
| `references/10-cors-vuln-report-priority.md` | 撞见 CORS 时 | **CORS 不挖** |
| `references/知识库/打穿短表.md` | **进站先看**（手法索引，一行一手法，指针指向模块） | 开场几枪 |
| `references/知识库/*.md` | 短表对得上、或现场需要细节时**只开那一篇** | **62 篇**实战模块（数会变，**以 `知识库/README.md` 现稿为准**；改库必对账） |

冲突时：挖什么 → `02`；报告 → 只跟 `03`；CORS 不挖 → `10`；白盒 → `06`；范围/持续挖 → `01`（压过「等继续」）；能力迭代落盘 → `04`。**知识库与 references 顶层规则冲突 → 以规则为准。**

## 1. WorkBuddy 环境适配（原包是 Grok 版，已按本机改）

| 原 Grok 用法 | WorkBuddy 用法 |
|---|---|
| `~/.grok/rules/*.md` | `.workbuddy/skills/src-hunt/references/*.md`（**项目级 skill**，仅本工作目录 `E:\codex_work\WorkBuddy_渗透` 下自动加载） |
| Playwright MCP（`playwright__*`） | **浏览器一律先加载 `agent-browser` skill**（本机已装，系统 Chrome 已配好）或 `playwright-cli` skill；不要自己写 bash 驱动浏览器 |
| FOFA MCP（`mcp_servers.fofa`） | `tools/fofa_MCP/` 已随 skill 落地；需用户在 `~/.workbuddy/mcp.json` 配好并自填 key（见 §6）。**没配就用 crt.sh / 手工 / 用户给的资产清单，不停工** |
| `~/.grok/config.toml` | `~/.workbuddy/mcp.json` |
| 桌面任务根 | **`C:\Users\86182\Desktop\{任务}_SRC挖洞\`**（`资产/` `js/` `报告/` `{名}_dig/` `README.md`） |
| 打 HTTP 枪 | **本机 Bash 的 PATH 是坏的**（`dirname`/`head`/`grep`/`ls`/`wc`/`tee` 全 command not found，每条命令 stderr 都会报 `dir: command not found`，可忽略）。**★修复法（2026-09-13 实测）**：命令最前面加 `export PATH="/c/Users/86182/.workbuddy/binaries/PortableGit/versions/1.2.0/bin:/usr/bin:/bin:$PATH"`，之后 `curl`/`grep`/`head`/`ls`/`sed` 立刻恢复正常，连带 `cd: null directory` 也消失；修不好时再退回下面的 python 兜底 → **别用 curl/grep/head 拼管道**，一律用**托管 python 绝对路径**跑脚本：`C:/Users/86182/.workbuddy/binaries/python/versions/3.13.12/python.exe`。HTTP 用 `urllib.request`（托管 python 无 requests），代理取 `os.environ.get('https_proxy')` + 直连兜底（端口每会话变），证书 `check_hostname=False` + `verify_mode=CERT_NONE`。起手先把上一任务的 `{名}_dig/probe.py` + `session.py` 复制过来（模板已封装 UA/代理/重定向）。整包要能复制进报告 |
| **SSH 打靶机 / 在靶机上编译验证** | Windows 侧 `ssh.exe` **不能非交互传密码** → 用 `paramiko`（已装在 `C:/Users/86182/.workbuddy/binaries/python/envs/default`）。**四条硬坑**：① 用 `exec_command` **逐条独立会话**，别用 `invoke_shell()` 持久 shell（sudo 提示会把 shell 卡死，且变量不跨行）；② sudo 一律 **`sudo -S -p '' <cmd>` 并从 stdin 喂密码**（不进命令行、不依赖时间戳；`sudo -n` 在无 tty 的独立会话间**不共享**时间戳，实测报"需要密码"）；③ 非英文 locale 下 sudo 提示是"密码："，用 `-p ''` 规避；④ 传文件用 `paramiko.Transport` + `SFTPClient`。**验内存类漏洞优先 ASan**：`./configure --with-cc-opt="-fsanitize=address -g -O1" --with-ld-opt="-fsanitize=address"`，运行必须 `ASAN_OPTIONS=detect_leaks=0`（否则启动期泄漏会让 `nginx -t` 返回非 0，`|| exit 1` 直接干掉脚本），加 `log_path=/d/asan` 落盘好读。**判"崩没崩"用 worker PID 集合变化 + `error.log` 的 `signal 11`，别信 exploit 工具自报的 Crash。** |
| **过动态防护（412/202 挑战）** | **默认 `tools/cdp/cdp.py`**（系统 py3.12 + 系统 Chrome，DETACHED 启动）。**「批量看一堆站长什么样」（判登录页/注册入口/渲染后 URL）用 `tools/cdp/cdp_batch.py`**——见 `tools/cdp/README_CDP.md` §五，含五条硬坑（Chrome 必须与驱动同一次 bash 调用、`--fresh` 会起不来、`/json/new` 要 PUT、urllib 要绕 http_proxy、必须 py3.12）。`tools/botgate/`（mitmdump + WS 重放）只在**需要把请求转出来批量改造/重放**时用。老的 `cdp_run.py`(绑 189)/`cdp_zt.py`(只 evaluate) 保留，新任务一律用 `cdp.py`/`cdp_batch.py` |
| 拉子线程 | Agent 工具（`general-purpose`）；**交付必须含迭代**（见 `04`） |
| GitHub | 代理 `http://127.0.0.1:7897`；`Could not resolve host` 先开代理 |

**禁止**把 email / FOFA key / 用户 Cookie 写进 skill 文件或对话正文。

## 2. 安全红线与授权（2026-09-26 用户定调）

> ★★ **总纲（最高优先级）**：**唯一「绝对红线 · 同意也不做」＝ DoS**（本条第 2 项）。
> **其余一切动作默认不做；用户明确同意后即可执行** —— 含**写操作**（改密/改绑/改资料/删除/提交）、
> **上传与落文件**、**执行型载荷**、**越权写**、**调 logout/注销/吊销**、**CORS**、**批量取数 / 真资损动作**。
> 默认仍**只读**；写与执行类**先说明、拿到同意再发**。
> ★ 本条**只解除"动作类"限制**；**第 1 项「禁测目标清单」属范围问题，不随之放开** ——
> 解禁需用户**专门点名**那一个目标。

1. **禁测清单（用户点名；★ 属「范围」非「动作红线」，不随总纲放开）**：`biz.sheincorp.cn` **及其全部子域**（`*.biz.sheincorp.cn`，如 `bbl.biz.` / `watermark.biz.`）—— 2026-09-17 指令「禁止探测」。
    **不发任何主动请求**（HTTP / 端口 / 路径扫描一律禁止）。已有静态字符串（如前端 JS 里出现的域名）可保留，但须标「**禁测，未探测**」。
    新增禁测目标：**先追加到 `AGENTS.md` 红线段**，再列表于此处。

2. **禁止 DoS —— ★ 唯一绝对红线（无例外）**（2026-09-18 指令「禁止dos」；2026-09-19 用户再次确认「不能 dos 攻击，会导致系统崩溃」；2026-09-26 用户明确「我的红线只有一个就是 dos」）：任何可能造成拒绝服务的动作**一律不做，且不因任何理由放开** —— 内存/CPU/磁盘耗尽载荷、并发压测、让服务崩溃或重启的输入、会打崩渲染进程/浏览器实例的输入。**用户同意也不能做，强制命令也不覆盖。**
    只做**单发、低量（单主机 ≤10 次/分钟）、非破坏性**验证。发现某输入会打崩服务（如渲染服务遇 `file://` 会销毁 browser 实例）→ **立即停止复现、记录现象，之后不再碰它**，报告中标注「未复现 / 不武器化」。
    ★ 与第 9 条档②的分界：**档②管「让目标执行我们提供的代码」，不管「把服务打崩」** —— 打崩服务属 DoS，无论如何不做。
    连带纪律：破坏性验证会烧掉出口 IP 可信度 ⇒ 优先**非破坏性 oracle**（类型错误 / PDF 文本回读 / 只读差分）。

3. **授权范围**：只在授权语境（SRC 范围 / 用户自有资产 / 用户明确点名）内测。默认已是授权研究语境，**禁止**开场盘问授权书、公司名、身份证明（`08`）。

4. **越权验证 · 最小伤害（默认手法）**：默认用读/列表差分证明跨用户跨租户（优先 GET/查询）。写越权**默认不做，需同意**（见第 10 条）；获同意后顺序是「先添加（看能不能挂别人名下）→ 再删自己刚加的那条」；**不要**改/删别人已存在的订单、地址、密码、角色。禁止批量、禁止真资损、禁止扣钱清库存（需同意方可例外）。

5. **登出/注销 —— 默认不做，需同意**：用户给了登录态后，**默认严禁**调 `/logout`、`/signout`、`/revoke` 等一切退出/吊销；不测「退出后会话还有效」。**用户明确同意后可做**（同意请求里须写明会不会踢掉用户自己的在线会话）。改绑/改密获同意后，**改得回就立刻改回原值**，改不回要在同意请求里事前说明。

6. **CORS —— 默认不挖，需同意**：**默认永久不挖**，勿开 `知识库/cors-test.md`。**用户明确点名要求时才做**。登录/重置/改绑/换票仍测。

7. **破坏性利用 —— 默认不做，需同意**：不跑真资损、不批量拖库、不写死马；只留可复核证据（整包 + 差分）。**用户明确同意后可按第 9 条档②执行。**

8. 清理任务夹时**绝不碰**浏览器保存的账号密码/Profile/Login Data（`05` §3.3.1）。

9. **执行型验证：分两类，别混**（★ 2026-09-19 用户定调后重划；分界 = **有没有必须先攻破的安全机制** × **副作用能不能事前算清**）
    **① 可做 —— 授权范围内，含生产：**
       · **只读最小命令证明**：`id` / `whoami` / 无害标记串。
       · **仅解析 / 无载荷回连**：DNS 型 OOB（`Inet4Address`、URL 解析、`dnslog` 域名一类），
         或**空响应 Listener**（只记录连接，**不下发任何 class、不返回任何可反序列化对象**）。
       纪律：**单发、低量、只读 / 无副作用、不落文件、不覆盖、不删改、不批量**；
       **先跑"无害标记"确认点真被消费，再上真值**；OOB 用**每次唯一域名**、不轮询；
       **优先自有 / 平台提供的 OOB**（public `dnslog.cn` 会把目标出口 IP 暴露给第三方，金融目标尽量避开）。
    **② 执行型载荷（含让目标执行我们提供的代码）：先向用户描述后果，取得用户明确同意后执行。**
       执行前必须向用户说明四项：
       · **① 载荷是什么** —— 投什么、怎么投（自控最小载荷优先：只做一件可枚举的事）。
       · **② 在目标上会发生什么** —— 哪一段被触发、执行到哪一步。
       · **③ 副作用与影响面** —— 能否事前算清、blast radius、是否影响生产业务。
       · **④ 中止与善后方式** —— 怎么停、怎么清、留了什么痕。
       —— **未取得用户明确同意 ⇒ 先问**；**用户给了同意 ⇒ 执行**（总纲：除 DoS 外，同意即可）。
       ★ **四项的内容不是"闸"，是让"同意"有意义**：尤其 **③ 里若含"不可逆 / 恢复不了"，必须写明**。
       ★ **lexin datashare（分档示例）**：2026-09-20 已终判收口，**无待表态项**。
       ★ **手法层不属 ②**（编码 / 位置 / 转义变形、绕规则本身随便试）；判定用的无害探针任何环境可用。
    拒绝时**必须同时给三条**：① 已实证到哪一步 ② 未实证的是什么、为什么不该由外部证明 ③ 替代路径（服务端自查 / 非生产实例 / 本地复现）。详见 `知识库/recon-methodology.md` §25 + §20.3。
    ★ 注：**「WAF 挡住了」不能作为降级理由**（datashare 亲例已实证 WAF 可绕，见 §22/§23）。
      ★★ **精确读法（2026-09-19 澄清，别误读成"必须去绕"）**：这条是**报告 / 定级**规则 ——
      不许因为"WAF 拦了"就把风险**降级**、或断言**"不存在"**（要写"**未测定 + 为什么没继续**"）。
      **它不是"必须绕过 WAF"的指令。** 要不要绕，取决于**绕完之后下游还有没有可执行的动作**：
      · 下游**可执行**（如绕过 `@type` 规则后能继续做无害判定）⇒ 绕；
      · 下游**不由我们产出**（如绕过关键字规则后，下一步是生成并投递字节码 / BCEL 串）⇒
        绕只买到一条**没有可执行下游的信息** ⇒ **不绕**，以「未测定 + 原因」入档。
      ★ 两条纪律别混：**"不能拿 WAF 当降级理由" ≠ "必须绕 WAF"**。
    ★ 报告定级认 `03`：`03` 的「严重」硬要求**命令跑起来** ⇒ **DNS 命中 / 连上一台 Listener 都≠命令跑起来**；
      只证到「可达 + 可绕 + 原语在工作 / 网络路径可达」的不得写严重（见 `03` 与 `知识库/recon-methodology.md` §25.4）。

10. **禁止擅自修改任何数据**（2026-09-23 用户指令 · 最高优先级；★ **2026-09-26 用户澄清语义**）：
    **改密码 / 改绑手机邮箱 / 改资料 / 删除 / 提交 / 上传落文件 / 一切会改变目标状态的写操作，一律禁止擅自执行。**
    要动之前必须**先告诉用户**（改什么、改成什么、影响面、怎么恢复），**取得明确同意后才可发**。
    **改密码 —— 任何情况下不自己动手**（用户自己做，或用户明确指名要求）。
    默认只做**只读**验证：渲染表单 / 只读校验口 / 读差分。
    ★ **2026-09-26 用户原话澄清**：「**只是你不能自己擅自，要告知我，我同意**」⇒
    **核心禁令是"擅自"**；**告知 + 同意 ⇒ 可执行**，不再以本条为由推回。
    ★ **禁止用「另一个接口会拦」外推「这个写接口也会拦」** —— 亲例（2026-09-23 dqManage）：
    `verifiersPassword` 对 `'a'` 返回"长度应至少8位"，据此以为写入口也会拦 ⇒ 实际 `updatePassword`
    **不复用该策略校验**、直接执行，把会话账号的密码改掉且**会话被服务端失效**。
    与第 4 条（越权最小伤害）、第 5 条（登出需同意）同源；`03` 的「改密…改不回就停在回包」是这条的**下限**，不是上限。

## 3. 起手三步（每次任务）

1. **判模式**：给了固定站/URL 清单/文档 → **锁面**（不主动 FOFA 出圈，但资产簇多 host、业务流子域、同 host 多 path 都要挖）；只给集团名/品牌名 → **自由跳**（种子尽能力多备，无条数上限）。
2. **建任务根**：`C:\Users\86182\Desktop\{任务}_SRC挖洞\`，含 `资产/` `js/` `报告/` `{名}_dig/` `README.md`；`{名}_dig/线程必读.md` 写「迭代见 `04-hunt-iter.md`」。
3. **自由跳必落盘** `资产/种子队列.md`（种子 | 类型 P0/P1/P2 | 状态 pending/doing/done/cold | 备注）。

## 4. 主节奏口令（背下来）

- **一种子闭环**：搜一个种子 → 去重去废去非存活 → **剩下的活面全部挖完** → 才搜下一个。**禁止**多种子一次搜完再挖。
- **深挖优先**：本种子还剩未挖活面 → 禁开新种子 FOFA；FOFA 条数不当进度；优质根域**只回灌不改道**；429/限流**只挖池**；多线程**禁双 FOFA 工厂**。
- **进站**：§4.0 用 3～5 行说清这摊（谁在用/核心对象/钱权状态落在哪/没登录能碰到哪层）→ 抽 JS（**不只是 path**：签名盐、硬编码钥、密文 id、hidden 路由、演示号）→ 建接口清单 → 全类型矩阵 → 打成了按 `03` 落 `报告/`。
- **力气顺序**：未登录出他主体 → 认证接管（§4.2.2）→ 换 id（不限字段名）→ 有号写/逻辑 → **四件套（注入/SSRF/XSS/RCE）打在有差分面的参上** → JS 钥匙。
- **不得连日空窗**：禁止连续多轮只堆未授权读/同构列表。四件套按栈选探针（不是每站只丢 `'`）；无入口才 N/A + 原因。
- **打开是登录页 ≠ 换资产**：先找业务面（`service=`/`redirect_uri=`/JS `baseURL`/302 Location/同品牌 `api`·`gateway`），主业挖未登录；登录表单看得见的面打通或证伪就停。
- **中危先升链**：同一对象还没走到「能写/能看别人/能接管/能执行」→ 先跟，不换站。
- **禁止停工问**：「要不要继续？」「其它品牌要不要也挖？」「下一步您看？」——自由跳未叫停就一直挖；队列全 done 走随机再搜/回扫新增。

## 5. 对得上再开（目标特征 → 模块）

进站先扫 `知识库/打穿短表.md`；**对得上就只开对应那一篇**，`知识库/README.md` 是反向索引。**禁止**每站通读整库（`04`）。打开模块 ≠ 只测表上那一枪。

| 目标特征 | 优先开哪篇 |
|---------|-----------|
| **用户丢来一份抓包（Yakit/Burp/mitm）说「挖这个小程序/APP」** | **`知识库/miniprogram-capture-token.md`** —— 锁面不 FOFA；只读导出→清单→**凭证定型**（RSA 密文/ticket/身份 Cookie，别把 acw_tc 当身份）→**三问判洞**（会不会过期/能不能吊销/会不会外带）→鉴权矩阵（原包 vs 剥凭证包比长度+业务码）→泄漏扫描（H5 URL query、Referer、埋点 ref 跨域上报）。含 Yakit 只读导出与 `\"` 转义的坑、重复密文指纹对比法 |
| **目标是 Android APP，且有 jadx 反编译源码（`app/<pkg>/`）** | **`知识库/android-app-whitebox-audit.md`** —— 覆盖度盘点 · 接口面 `super(route,controller,action)` · **抓包一定要导 JS**（Web 端接口常不在源码里，是另一套后端）· ★**参数名别猜**（从 chunk 调用点读）· 签名校验 Verify-first 三段式 · **JSBridge 检查清单**（能力面 / 安装时机 / iframe 绕过）· 避坑（证书校验、测试包死代码） |
| **请求体是 `{"body":"<base64密文>","secRamSt":"..."}` / 路径成片 `/pub/` / 有 `getFork`（运营商 dcp·集中运营类小程序）** | **`知识库/mobile-dcp-gateway.md`** —— 「加密+签名」是纸糊的：签名盐在前端、`getFork` 未授权白送一对 RSA 密钥。掏空算法后用 `tools/dcp/dcp_gateway.py` 自造请求，专看 `/pub/` 里吐内部数据的口。**含一条撤稿反面教材**：四川移动那组「员工名单→明文手机号」看着像高危，回读页面才发现是 tabBar「附近厅店」+ 商品详情「咨询营业员」的公开拨号业务 → 撤稿。该文给出**比三条闸更前一步的闸**：判未授权前先问「这数据产品里本来是不是就给未登录用户看的」，并给出找页面归属的方法（搜接口名 + `currentFile:'pages/...'`） |
| 有用户体系（注册/登录） | `知识库/idor-test.md`（越权）+ `知识库/authbypass-test.md`（任意登录/接管，§4.2.2） |
| 有搜索/筛选功能 | `知识库/injection-test.md`（注入） |
| 有文件上传 | `知识库/file-upload-test.md` |
| 有内容请求/预览功能 | `知识库/ssrf-test.md` |
| 有评论/留言/富文本 | `知识库/xss-test.md` |
| 有支付/优惠券/积分 | `知识库/logic-test.md` + `知识库/race-condition-test.md` |
| 接口返回字段多 | `知识库/info-leak-test.md` |
| GraphQL 接口 | `知识库/graphql-test.md` |
| OAuth/JWT/SAML 认证 | `知识库/oauth-jwt-test.md` |
| WebSocket 实时通信 | `知识库/websocket-test.md` |
| API 网关/微服务架构 | `知识库/api-gateway-test.md` |
| CDN/缓存服务 | `知识库/cache-poisoning-test.md` |
| AI/LLM 功能 | 对话口工具真执行走 `知识库/agent-tool-exec-test.md`。**禁开** `llm-security-test.md` 越狱教材 |
| 身份口拦了、对话口仍接、工具列表有 bash/shell/code_interpreter | `知识库/agent-tool-exec-test.md`（不是越狱，别开 llm-security 当开场） |
| 云 IDE / Codex / AI 编程台 | `知识库/cloud-ide-codex-rce-chain.md`（弱口令 → `/codex-api/rpc` RCE） |
| 前后端分离架构 | `知识库/http-smuggling-test.md` |
| 返回 401/403 | 先分清：登录页 → §4.1.1 找业务面；认证口走 §4.2.2；**不要**开 `401-403-bypass` 磨登录 HTML。业务 API 的 401/403 现场改 path/METHOD/头自己打 |
| 公网已见 Redis/rsync/FPM/AJP/YARN/2375/h2-console | `知识库/info-leak-test.md` §五（见了才打）+ 对应 `ssrf`/`jndi`/`path-traversal` |
| 有 CORS / 跨域接口 | **跳过**（不挖，**勿开** `cors-test.md`）；转注入/越权等 |
| **手上有一堆绕过手法/工具，不确定该不该绕、绕了有没有用** | **`知识库/waf-bypass-strategy-selection.md`** —— **绕过策略前置三问**（先判该不该绕、执行点存不存在，再选技术）；★ `WAF 绕过 ≠ 注入存在`。与 `waf-bypass.md`（payload 变形，权威）`/waf-bypass-parser-layer.md`（解析层差异）**四文件分工**见各自文首 |
| 有状态变更写操作 | `知识库/csrf-test.md` |
| 有 WAF 拦截 | **先开 `知识库/waf-bypass-parser-layer.md`**（§8 决策树：先判「静态检查型 vs 动态 JS 挑战型」，再按 体积→体格式互换→payload 变形→Ghost Bits 打）；payload 变形与厂商矩阵见 `知识库/waf-bypass.md`。★ **若被拦的是「框架特征字面量」（`@type`/`$ref`/OGNL/SpEL/`ac ed 00 05`/`O:N:"…"`）→ 直接跳 `waf-bypass.md` §2.1b**（框架宽容解码 > WAF 严格解码，实测能穿腾讯云 WAF）；厂商矩阵含腾讯云 WAF 专章（§8） |
| 返回 412 / 202 + `$_ts` / `_$$q()` 动态挑战页（瑞数/顶象类，动态 cookie + URL 被注入动态参数） | **★默认直接上 CDP，不许绕开不打**（用户 2026-09-17 定调）：`E:\codex_work\WorkBuddy_渗透\tools\cdp\cdp.py` 三步走 `open <url>` → `xhr <api>` → 拿数据；profile 按 host 隔离、412/202 自动 reload 重试、**必须系统 py3.12**（托管 py3.13 无 websockets）；用法与坑见 `tools/cdp/README_CDP.md`，离线自检 `tools/cdp/_selftest_cdp.py`。原理与备选路线见 **`知识库/river-security-bypass.md`** —— 三件套（Cookie1 服务端下发 / Cookie2 VMP 生成 / URL 后缀参数）缺一即 412；四条路线（中间人转发 / Node 补环境 / 引擎级指纹 / 纯算法 rs-reverse）；含 189.cn 实测。**注意：412→400 不算绕过，拿到业务数据才算** |
| 路径/下载/读文件 | `知识库/path-traversal-lfi-test.md` |
| XML / 文件解析 | `知识库/xxe-test.md` |
| Java 反序列化 / 中间件 | `知识库/deserialization-test.md`（★ 2026-09-19 补 **fastjson 专章**：异常原文指纹 `can not cast to JSONObject.` / `autoType is not support. <类名>`；**判 autotype 状态必须用三类探针**（⛔ 别用"不存在的类名"——零信息量；`java.lang.String`/`Integer` 被放行只能证明"不是全局禁用"，**不足以判"放行态"**）：`java.util.Locale`/`BigDecimal` → `create instance error` = **放行态**；黑名单成员 `java.lang.Thread`（**空对象**）→ 被拒 = **黑名单在生效**；完整判读矩阵见 `recon-methodology.md` §24；WAF 绕过指向 `waf-bypass.md` §2.1b；报告口径与修复）+ `知识库/jndi-injection-test.md` |
| Laravel 开 debug（`/_ignition/health-check` 200 且 `can_execute_commands:true`） | `知识库/deserialization-test.md`（CVE-2021-3129）。**零写入验补丁法（先做这个，别急着走写链）**：补丁 `isSafePath()` 要求 `viewFile` 以 `/` 或 `./` 开头**且**以 `.blade.php` 结尾，所以拿**缺失文件**当探针即可判别 —— `…/zz_nope.txt` → 200 空 = **闸拒(已修)**；`…/zz_nope.blade.php` → 500 `failed to open stream` = 过闸(真去读)。只触发 `file_get_contents`、不触发 `file_put_contents`，**零写入**。判出「已修」就收工，不需要用户授权。若未修：`MakeViewVariableOptionalSolution` 是「读→替换→写回」的**写**原语、**读不出 `.env`**，RCE 必走写链（清日志→投毒→`phar://`），属破坏性，先要明确授权。WAF 若只扫 body，把 `parameters[viewFile]` 挪到 **query** 即可绕过 |
| 子域/资产接管线索 | `知识库/subdomain-takeover-test.md` |
| **用户在 Yakit / Burp 里抓了包，让你「连 MCP 看看」再接着测**（抓包可能含**他自己账号的登录态**） | **`知识库/yakit-mcp-forensics.md`** —— ① **MCP 端点** `http://127.0.0.1:11432/mcp`（Yaklang MCP v0.0.2，~149 工具），`initialize → notifications/initialized → tools/list`，**必须带响应头里的 `mcp-session-id`**（缺了报 `Missing session ID`）、**必须绕系统代理**（`--noproxy '*'` / `ProxyHandler({})`）；若工具没进自己的工具表，**直接按协议 HTTP 调即可，别收手**。② ★★ **别用 MCP 解析报文**（中文被转义成 `\x`，整段不是合法 JSON → `Invalid \escape`）⇒ **MCP 负责「发现」、sqlite 负责「取证」**：库路径从 `query_http_flow` 响应的 `current_database` 白送，只读打开要处理 **WAL**（打不开就复制 `db+-wal+-shm` 三件套），列名是 **小写**，`request/response` 是整包转义文本且**值带外层引号**（`for cand in (raw, '"'+raw+'"')`），**必须二进制落盘**（文本模式把 CRLF 变 `\r\r\n`）。③ **别忘了翻 `web_fuzzer_tasks` / `web_fuzzer_responses`** —— 用户自己跑过的请求带关键意图（`ResponseRaw` 是 base64 整包）。④ ★ **证伪「未登录下发凭证」要三组独立 session**：A1 无 Cookie / A2 再开一个无 Cookie / D1 带真实会话，**三者逐字节相同 ⇒ 固定公开常量**（本轮 `verify_info.json` 的 `app_key` 就是这么证伪的）；再补双证——该值是否**本来就在别处的公开 URL 参数里**。⑤ 用用户会话**只读**跑「登录态矩阵」拿真实功能面，**绝不碰 submit/save/login/register/smscode**。⑥ 抓包能挖的六类线索：敏感凭证走 GET（CWE-598，密码 MD5 可重放=等价明文）、JS 常量表里没有的**新前缀/host**、`operator/creator/audit_user` 等**内部字段**、测试数据残留（`<script>` 只能证"输入未过滤"，**不能直接定 XSS**）、`octet-stream` 加密体网关、`307 + Server: stgw` 强制跳 HTTPS。★ **若这次目标是微信小程序 → 必须并行读 `知识库/miniprogram-capture-token.md`**（§7 本地缓存解包 / §8 全量接口清查 / §9 密钥专项 + 认钥闸）—— 两篇是配套的，只读本文会漏掉「解包」主线（2026-09-21 理想案亲例：起手只按「连 MCP」选了本文，漏读那篇，到第四轮用户提醒「包不是在本地吗」才补上解包，白走一轮） |
| **用户丢来一份固定域名清单，要「探活 + 分类」（免登录 / 可注册 / 仅登录）** | **`知识库/recon-methodology.md` §14** —— 锁面「探活+三分类」工作流。★**最大的坑：SPA 的「能不能注册」绝不能用路径探测判**（`/login`·`/register`·`/api/` 对 SPA 全返回同一外壳、同状态码同体积 ⇒ 零信息量），**必须用 `cdp_batch.py` 渲染后看按钮文案**。含三分类硬判据（手机号验证码「首登即建号」也要归「可注册」）、`502 不知道这样的主机`=代理侧 NXDOMAIN 别当活资产、TLS 握手失败≠站点死（换 curl/降级 http）、crt.sh 对中文金融域收益极低（通配符证书未入 CT）⇒ 改走 `dns-prefetch` / SSO `?url=` 参数解码扩面。★ **2026-09-18 补 §15（重要）**：**SPA 的 chunk 大面积返回 `200 text/html` 且长度与首页外壳相同时，别判"部署残留"—— 先回 `index.html` 读 `<script src>` 的真实绝对地址**（亲例：浏览器请求 `open.fenqile.com/static/js/8x.js` 全被 SPA 兜底成 7183B HTML，真实 CDN 是 **`cresauth.fenqile.cn/work-loan-open/static/js/`**，换上去 83 个 chunk 全 200 全真 JS 共 6.5MB）。收益：接口清单 **27 → 108 个 `/route*` + 15 个 channel**、后台路由 0 → 40+、参数语义可直接读（如全站对象 `business_id` 来自 `localStorage`）。含 **①用 chunk 判存储型 XSS 的四条件**（`dangerouslySetInnerHTML` 命中要先看是不是 react-dom 内部；React `createElement` 第三参数=children 自动转义 ⇒ **库里存 `<script>` 只证"输入未过滤"，不够定 XSS**）；**②判越权的"先证明自己本无权"基准法**（`account/info` 显示自己 `business_id` 为空 ⇒ 传 `business_id=1/2/100` 被专用拦截 `10981283`「商户不允许越权访问，商户【】没有访问商户【1】数据的权限」⇒ 反而证明服务端有权限比对层）；**③判定脚本别把 `"result":0` 当"有数据"**（会把 `19261002 输入参数错误` 误判成未授权）。★ **2026-09-19 补 §16/§17**：**网关「请求跨域了 / 暂无权限访问」的来源校验用「固定基线 + 6 组对照」判**（基线 / 不带 Referer·Origin / Referer=站点根 / 同族子域 / `Origin: null` / 外域；**6 组逐字节一致 ⇒ 判定不基于 Referer/Origin，是服务间来源限制 ⇒ 公网无参照物，判"不成立"且不伪造 XFF·不改 Host 硬顶**；亲例 6 组全同仅 `rc_gateway_ip` 随 LB 变 ⇒ 顺带拿到**内网 IP 泄漏**的低危 + 网关错误码）；**同族系统交叉对照一次定位路径属于哪个网关**（网关 JSON=有效路径 / SPA 外壳=不在此站网关 / Spring 默认 404 JSON=独立 Java 服务）。★ **§17 环境坑：`python -u x.py \| head -N` 会 SIGPIPE 杀脚本**（表现为 exit=0 但落盘文件一个没生成）⇒ **长脚本输出一律 `> log 2>&1` 重定向，禁用管道截断**。★ **2026-09-19 补 §18（★ 该法直接挖到一个中危）**：**批量打网关接口时盯住「哪一个响应跟其他不一样」** —— 亲例 150 个接口里 **148 个**整齐返 `19002028 您还没登录`，**只有 2 个**返 `10001 参数url缺少` ⇒ **参数校验跑在登录校验之前（校验顺序缺陷）** ⇒ 补参即跳过登录 ⇒ 未登录拿到**企业微信 JS-SDK 签名**（`jsapi_ticket` 衍生物）。定中危的决定性一步：**换参数值看输出是否跟着变**（`url=站内`/`example.com`/`1` → 三个不同 signature ⇒ 服务端真为调用方给定 url 签名、**无域名白名单**）。同时给出「`url` 参数**不是 SSRF**」的判据（换任意值响应形态与耗时不变、只在签名值上有差异 ⇒ 它是签名算法输入），以及纪律（补参只用无害值，**绝不传内网/云元数据/localhost/`file://`·`gopher://`**；拿到签名即止步，**不拿它去实际调下游平台**；报告写明"证明了什么/没证明什么"） |
| **用户丢来一份扫描器导出的资产清单（TscanPlus / FOFA / 灯塔 / Xray 的 JSON·CSV），问「有没有 n-day / 已知漏洞」** | **`知识库/rendering-service-rce-triage.md`**（渲染服务专属）或 **`知识库/scanner-fingerprint-n-day-triage.md`**（通用 n-day）—— 前者见下一行；后者 ★**铁律：先证伪指纹再谈 CVE**（亲例 SHEIN 259 条：`Apache-Struts2`82 / `用友nccloud`38 / `Citrix`10 / `AWSS3`10 / `senayan`2 **全是误报**，真面只有 12 台）。含五类高频误报成因与一眼识别法、前端库版本→CVE 对照表、WebLogic/APISIX/Spring Actuator/Next.js/NGINX-42945/OSS 的**只读验证手册**、两个必建习惯（**先分清「业务 403」与「WAF 拦截页」**；**枚举前先估封禁阈值**，亲例 ~16 次 WebLogic 路径枚举即触发全域 IP 拉黑）。★**2026-09-18 补 §5~§7**：**组件只读指纹 oracle**（Exchange 端点矩阵+FEServer / Drupal Generator meta+主题资源存在性 / Tomcat 404 页页脚+AJP 单连接 / Tengine「无法确认也是结论」/ OSS 三种列举）、**误报第三型「网关·SPA catch-all」**（对同一 host 打 ≥3 个语义不同路径看是否**逐字节相同**；亲例 api.fenqile.com 7 路径全返同一 45B JSON ⇒ Actuator 全误报）、**Akamai 前置目标枚举阈值极低**（~20 次只读 GET 即被**按 host** 全路径 403，同时其它 host 正常 ⇒ 见到某 host 突然全 403 先怀疑自己被限流，别当成目标配置） |
| **拿到渲染器内 JS 执行后，想再往前一步：读本地文件 / 读别的 origin / 绕 `file://` 限制 / 判"沙箱能不能逃"** | **`知识库/chromium-browser-policy-layering.md`** —— ★**先判层，判错层 = 白干一轮**：①**渲染器（Blink）**只做快速检查，`Not allowed to load local resource` 这句就是它抛的；②**浏览器进程**才是**权威**（`ChildProcessSecurityPolicy`，`GrantRequestScheme`/`GrantCommitScheme`/`GrantReadFile`，渲染器**无自授权接口**）；③OS 沙箱。**①与②是两层独立校验 ⇒ 渲染器 RCE 单发不够，读文件必须再有「策略绕过」洞（官方 CVE 描述一律写明 "who had compromised the renderer process"）**。可改策略的只有 `--allow-file-access-from-files` / `--disable-web-security` / 扩展 `file:///*` —— **攻击者全不可控**；`allpaca/chrome-sbx-db` 的 Mojo 提权 PoC **全 ≤M-83 且需 MojoJS 特权绑定，网页内不可达**。含**安全实测判据**（`featurePolicy.allowedFeatures()`、`userActivation`、picker 的 `SecurityError`、OPFS/webkitFS 作对照）与两条纪律：**别穷举 `file://` 变体**（每次试都会销毁一次浏览器实例）、**快照 oracle 里 I/O 绑定的 async 读不到、但微任务级 Promise 能读到** |
| **目标是一个「服务端跑浏览器」的服务（HTML→PDF / 导出 / 截图 / 报表 / SSR），已确认能执行任意 JS，用户问「能不能 RCE」** | **`知识库/rendering-service-rce-triage.md`** —— ★**先分清「执行 JS」与「执行系统命令」**（`typeof process/require` 在 ⇒ Node 上下文 = 直接 RCE；只有 `window/document` ⇒ 渲染进程，必须再有引擎漏洞）。**六步判定**：①上下文类型 ②**★`typeof WebAssembly`**（禁了 ⇒ 最成熟的 CVE-2021-30551 链「覆盖 WASM RWX 页写 shellcode」直接断，公开 PoC 基本失效）③`SharedArrayBuffer` **能否真构造** ④精确 build（⚠️**UA 可能被服务端改写**，亲例 `navigator.userAgent === "IE"`，改看 PDF `/Skia/PDF mXX`）⑤`file://`/出网（**file:// 被 Chromium 浏览器级策略拦，与 OS 沙箱无关** ⇒ `--no-sandbox` 也读不到文件）⑥**localhost CDP 9222/9223**（有则是最直接控制面）。含 **the-map §9 五路径检验清单**、GitHub 公开利用链适用性速查（**chrome-sbx-db 全 ≤M-83 且需 MojoJS 特权标志 ⇒ 不适用**）、**两个工程约束**（`page.pdf()` 0.5~1s 触发 ⇒ 异步结果会丢、必须同步写 DOM；hex 字符码输出避开 Identity-H 字体丢字；WAF 敏感串运行时拼接）、**⚠️ `file://` 是渲染服务的自毁开关**（一个 `<img src=file://…>` 即让 browser 对象 disconnect，单发 0.36s；自愈常 <1s ⇒ 未必是 DoS，但**有 DoS 红线时一律不复现**） |
| **某个免登录 / 未授权服务接口，想知道它的「配置字段」到底能干什么**（渲染·转换·导出·截图类服务最常见，config 里常同时封着文件写入路径、代理、输出目录、模板路径） | **`知识库/unauth-service-config-field-triage.md`** —— ① 从已落地前端 SDK 反推 schema，★**`__rest` 的「白名单假象」**（`__assign(白名单对象, rest)` 会把**所有未列出的键原样透传**，所以别把 PropTypes 列表当白名单）；② **类型污染 oracle**：给字符串型字段递 `true`/`12345`，响应出现 Node `ERR_INVALID_ARG_TYPE`（`The "path" argument must be of type string. Received type X`）⇒ 该参数被交给了 `fs`/`path`/`child_process`，**零副作用**（亲例 SHEIN `pdf.dotfashion.cn` 的 `config.download` 正是这样定性的未授权任意文件写入）；③ **同步错可见 / 异步错被吞** ⇒「传目录进去没报错 ≠ 这个参数没被使用」；④ **procfs 双面安全 oracle**（`/proc/self/cmdline`：读=白送内容，写=内核拒绝零副作用）分读/写；⑤ 同一参数**换 query 与 body 两种传法分别测**（亲例：body=文件路径、query=布尔开关）|
| **批量看页面 / 被 WAF 拦怕了要"低感知"打点** | **`tools/cdp/cdp_batch.py`**（批量渲染，判登录页/注册入口/渲染后 URL）+ **`tools/cdp/cdp_slow.py`**（★低频浏览器内探针：真实 Chrome 页面上下文 fetch、随机 6~12s 间隔、拦截页自动熔断）—— 见 `tools/cdp/README_CDP.md` §五，含五条硬坑（Chrome 必须与驱动同一次 bash 调用、`--fresh` 会起不来、`/json/new` 要 PUT、urllib 要绕 http_proxy、必须 py3.12）。**实测对比：Python 裸打 16 个路径即被 WAF 全域拉黑，换 cdp_slow 打 30 个请求零封禁** |
| 第三方 CVE 利用工具 / 网上脚本 报「SUCCESS / RCE executed / 已执行」 | **先读它的 `success` 判据源码，再决定信不信。** 典型坑（nGixshell 亲例）：`success` 其实 = "socket **0.2s** 内没收到数据"的超时启发式 → 公网跨洋链路（目标实测单次请求 **0.93~4.21s**）**必然误报**；地址来自硬编码 build profile、注释写明 `Requires ASLR disabled on target`，且版本识别失败（`Version: unknown`）时**静默回落到 `_default`**；`--cmd` 模式**没有回显通道**（`system()` 输出进 worker stdout → 守护进程下是 /dev/null），只有 `--shell` 反连或 OOB 回连才算证据。**三步核对**：① 看它依赖的路径/方法在目标上是否真成立（例：喷射路径 `POST /upload` 返回 404/405 → 喷射空转 → 伪造 `ngx_pool_cleanup_s` 根本没落地 → 逻辑上不可能 RCE）；② 同一地址多次 try 结果**翻面** = 延迟抖动，不是确定性内存破坏；③ 与自己独立的崩溃式检测交叉比对。**唯一可信验证 = 带外回连（DNS/HTTP）> 盲写读回 > 服务端自查配置。** |
| 被问「某站有没有 CVE-2026-42945 / NGINX nginx rift」或 `Server: nginx/<ver>-<brand>` | **★最快的排除法（先做这个，30 秒定生死）**：`grep -rn 'rewrite' /etc/nginx/` **为空 = 不受影响**（漏洞就在 `ngx_http_rewrite_module`，没有 `rewrite` 指令就没有可执行代码）；远程可验的等价指纹：`GET /index.nginx-debian.html` 返 **200** = Ubuntu/Debian **发行版默认站点**（`apt install nginx` 的默认 server 块零 rewrite，且 `/` 只有 615B "Welcome to nginx!"）→ 同样**必然不受影响**。**先判版本串真伪**：`nginx/1.21-altair` 这种 `<版本>-<品牌>` 后缀 = 人为改写（亲例：站长 2014 老博客自述"源码编译 + 改成 `nginx/1.5-altair`"）→ **`Server` 头不可当权威版本**，去站内归档/老页面（`/growl/`、blog、`-old` 页、robots 列出的目录）交叉验证。漏洞本体：`ngx_http_rewrite_module` 堆溢出，影响 0.6.27–1.30.0（修 1.30.1/1.31.0）；触发要求同作用域内 `rewrite`（**替换串含 `?`**）+ **未命名捕获 `$1/$2`** + 紧随的 `rewrite`/`if`/`set`。**外部没有零影响检测法**，只有崩溃式。做法：金丝雀 3/3 通过 → 对照组 5000B 普通长 URI → 逐候选前缀发 `GET /<prefix>A*349+*969`（溢出 = 2×`+`数；再补一档 `+*3500` 提高命中率）→ 看 early-close / 5xx / 后台探测缺口。**必做的排除项**：先排 `catch-all rewrite → 前端控制器`——若任意路径回的是静态自定义 404 而非应用输出、且 `/index.php` 404、非 GET/HEAD 全 405 → 该模式不成立。结论只能分「版本层（大概率受影响的版本）」与「配置层（实测无触发点）」两级；**定论必须站主本机**跑 `nginx -V` + `grep -rnE 'rewrite[^;]*\?[^;]*;' <conf_dir>/` 看后面是否紧跟引用 `$1` 的 `set`/`if`/`rewrite`。 **要复现**则三件套缺一不可：① `rewrite` 替换串含 `?` + **未命名捕获**（命名捕获 `(?<x>..)` 走长度正确的另一条路径，这就是官方的缓解法）；② **紧跟** `set`/`if`/`rewrite`（nGixshell 自带 lab 的 `env/nginx.conf` 就漏了这句 `set` → 它自己那个 lab 复现不出来）；③ 喷射路径必须是 **`proxy_pass`/`fastcgi_pass` 这类会读 body 的 location**（静态 location 对 POST 回 405、不分配 body → 喷射无效）。**RCE 另需** `sysctl -w kernel.randomize_va_space=0` + `calibrate.py` 在**目标机上以 root** 标定 `heap_base/libc_base/sys_offset/offsets`（注意 CLI 只有 `--heap-base/--libc-base/--system-addr`，**offsets 只能改 `KNOWN_BUILDS` 字典**；`--build` 按 `Server:` 头自动匹配 key）。**判定崩溃不要用工具的 "Crash" 字样，用 worker PID 集合变化 + `error.log` 里的 `exited on signal 11`。** ★**反连 IP 坑**：工具 `_local_ip()` 用 `connect(("8.8.8.8",80))` 取**出口网卡** IP，跨网段（VMware NAT 靶机 vs 多网卡宿主机）必错 → 要显式 `--listen-ip <靶机可达的宿主侧地址>`（如 VMnet 的 `x.x.x.1`）+ 放行防火墙端口，否则 RCE 成功也看不到 shell。 |
| Host / 缓存 CDN | `知识库/http-host-header-test.md` + `知识库/cache-poisoning-test.md` |
| 要抽接口/钥匙 | `知识库/js-reverse-guide.md`（页/JS 里的演示号当钥匙；登录框字典不当必做） |

**WAF 拦了再开**：有差分面的参被拦了，才开 `知识库/waf-bypass.md` 换编码/换位置。**禁止**开场对每个 path 丢 `'` 当 WAF 检测。

**★★ 命中「WAF 拦 `@type` / `$ref` / OGNL / SpEL / 框架特征字面量」→ 先开 `知识库/waf-bypass.md` §2.1b**
（**权威位置**；`deserialization-test.md` fastjson 专章有指纹与探针，`recon-methodology.md` §23 是完整案例 + 处置纪律）。要点：
① **别因为「标准 `\u0040`/`\x40` 也被拦」就判定无解** —— **这绝不代表无解**：WAF 解得了**标准**转义，但**解不了后端解析器的宽容变体**；
② 正确动作 = **去读后端解析器自己的解码实现，找它「比 WAF 宽容」的点**。fastjson 实测可过腾讯云 WAF 的 5 种写法：**`"\x4Jtype"`**（`\x` 第二字符任意非 hex，digits 表未占位即 0）、**`"\x4_type"`**、**`"\u００４０type"`**（全角数字）、**`"\u๐๐๔๐type"`**（泰文数字）、**`"\u００４０\u0074…"`**；
③ ⚠️ **公开资料的「混合编码 `\x40\u0074…`」对腾讯云单独用无效**（实测拦 501）—— 公开手法**必须对本厂商实测**；
④ 判「autotype 状态」**必须用 §24 的三类探针法**：⛔ **别拿"不存在的类名"当探针**（fastjson 对加载不到的类固定抛 `autoType is not support.`，**与开关无关，零信息量**，我曾据此判反过）；✅ 用 **`java.util.Locale`/`java.math.BigDecimal`**（存在、无无参构造、非 gadget）→ `create instance error` = **放行态**；用黑名单成员 **`java.lang.Thread`**（**空对象**形式，不给 `target`）→ 被拒 = **黑名单在生效**；`java.lang.Class`+`val:"java.lang.String"` → `can not cast to JSONObject.` = `@type=Class` 被执行。**⛔ 判出"放行态"后不要顺势投真 gadget 闭环**；
⑤ 报告只能写「未授权可达 + WAF 可绕过 + autotype 机制在工作 ⇒ 须服务端核查版本/safeMode/名单」，**禁止写成「存在反序列化 RCE」**；**「WAF 挡住了」不能作为降级理由**。

**nuclei 只是辅助**：主路径认 `01` §4，**不是**扫漏洞。只在需要已知 CVE / 暴露面（actuator、swagger、已知中间件）时辅助；**禁止**把「全量模板扫一遍」当本站矩阵或进度，不当开场必跑。

## 6. 白盒

用户给项目路径或源码 → 按 `references/06-researcher-blackbox-whitebox.md` Phase 0～6（心智模型 → 变体分析 → Sink 逆向 → 框架专项 → 深层 → 验证）。过程输出用该文件 §4.1；**黑盒 SRC 正式报告仍只认 `03`**。

## 7. FOFA 测绘（可选配件）

`tools/fofa_MCP/` 已随 skill 落地（`fofa.py`，主号 → backup → backup2 自动切，限流即切）。启用步骤：

1. 安装 uv（本机暂无）：`pip install uv`，或把 `command` 换成已有的 python 解释器路径。
2. 在 `~/.workbuddy/mcp.json` 的 `mcpServers` 下加：

```json
"fofa": {
  "command": "uv",
  "args": ["run", "--directory", "E:\\codex_work\\WorkBuddy_渗透\\.workbuddy\\skills\\src-hunt\\tools\\fofa_MCP", "python", "fofa.py"],
  "env": { "FOFA_EMAIL": "", "FOFA_KEY": "", "FOFA_EMAIL_BACKUP": "", "FOFA_KEY_BACKUP": "", "FOFA_EMAIL_BACKUP2": "", "FOFA_KEY_BACKUP2": "" },
  "enabled": true
}
```

3. 在连接器管理页对新 server 点「信任」才生效。**key 由用户自己填，禁止代填/代抄/贴进对话。**
4. 没配或限流 → 走 crt.sh / subfinder / 用户 `资产/` / 进站 JS 带出的范围内 host，**不停工**；节奏仍认 `01` §1.5。

FOFA 最短语法见 `references/知识库/recon-methodology.md` 文首——**它不是开场**。

## 8. 一句话

先判锁面/自由跳 → 建任务根与种子队列 → 一种子闭环（搜一个→清洗→挖完剩余活面→才换种）→ 进站先说清这摊、抽 JS 钥匙、建清单 → 全类型矩阵（四件套打在有差分面上）→ 打成了按 `03` 落 `报告/` → 中危先升链、高危先打穿 → 空转自纠，**禁止问「要不要继续」**。

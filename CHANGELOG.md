# 变更日志

本文件记录 **Ravenholt**（本仓库）的版本变更；版本号与 `app.py` 中的 `version` 保持一致。

> 本项目曾用名 **Z3r0 / XuanMu**，其历史版本条目已不再维护——本文件从当前版本重新起记。

---

## [Unreleased]

### 新增

- **测试结束自动总结**：每轮扫描收尾（调用 `finish_scan` 或本轮产出新 finding）后，平台按落库状态自动追加一条「测试总结」：已验证漏洞（平台重放复现）/ 疑似漏洞（有请求包但复验未通过）/ 无法验证（无请求包、纯配置、纯源码、OOB 不可用），并列出 `needs_follow_up` 的未完成测试面。总结由平台确定性生成，不依赖模型措辞。
- **报告路径支持可重放请求包**：`create_vulnerability_report` 新增 `request_url` / `request_headers` / `request_body` / `baseline_status` / `baseline_body` / `probe_status` / `probe_body`。报告镜像落库前由平台保存证据并重放，`reproduced` 才置为「已验证」；缺包、复验失败或 `refuted` 保持「疑似」。
- **沙箱镜像内置 hurl 8.0.1**：支持可评审的多步 HTTP 请求链与断言；其兼容库（libxml2 / libicu72）隔离在 `/opt/hurl/lib`，仅对 hurl 进程生效，不影响系统库。
- **构建代理透传**：`sandbox/build.sh` 在宿主设置 `HTTP_PROXY` / `HTTPS_PROXY` 时自动透传给 `docker build`（`NO_PROXY` 一并传递）。
- **资产规模治理**：项目资产导入上限提升到 5000；项目列表只带前 50 条资产、快照前 1000 条、图前 600 节点；新增资产分页接口与 `list_project_assets` 查询工具；编辑弹窗分页回填全部 scope 资产。
- **发现页紧凑排版**：卡片两行、去掉描述预览；顶部严重度统计条（全部 / 严重 / 高危 / 中危 / 低危 / 信息）可点击过滤。

### 变更

- **每份报告都必须有可重放证据（不分等级）**：`create_vulnerability_report` 在缺少完整 replay 包时直接拒绝（不再只限高危/严重），要求改用 `record_evidence`，或填 `replay_exempt_reason`（≥10 字，说明纯配置 / 纯源码 / OOB 回调不可用）；正文会注明「未附带可重放请求包」及理由。`poc_description` 增加 ≥20 字下限，必须写清请求、载荷与观察到的响应；证据路径 `record_evidence` 同样要求 ≥20 字的 `poc_description` 与正的 `baseline_status` / `probe_status`。`update_vulnerability_report` 允许给已落库报告补 replay 包或 `replay_exempt_reason`（同一次修订可调级），但不允许无包上调等级（依赖类报告不受此限），堵住绕过通道。
- **报告正文**：长度上限由 8000 提升到 30000；危害面取 `impact` 的第一条列表项并跳过导语；第五段只放复现步骤，`evidence` 独立为「证据摘录（agent 自述，非平台重放）」。
- **授权范围注入**：无论用户导入还是 agent 发现，都按主域 / 主机折叠注入，不逐条进入提示词。
- **沙箱镜像构建**：Debian builder stage 在构建时切换 apt 源到国内镜像，避免代理证书校验失败与直连超时。

### 修复

- **思考过程中无法滚动思维链**：思考块在每次流式增量后强制把内层 `scrollTop` 设为 `scrollHeight`，覆盖了用户的手动滚动，表现为「必须等思考结束才能翻」。现在用户向上翻看即暂停自动跟随，滚回底部后自动恢复；展开 / 收起面板时重置为贴底。
- **沙箱 `/app/.venv` 在系统 Python 升级后失效**：Kali rolling 已升级到 Python 3.14，上游镜像里建于 3.13 的 venv 看不到原 site-packages，`jwt_tool` / `requests` / `caido-sdk-client` 等全部 import 失败；现在构建时按当前 Python 重建 venv 并装回上游依赖。
- **证据路径 finding 过不了报告结构门**：`record_evidence` 原先不关联资产，线上 `report_gate.require_asset=true` 时即使复验 `reproduced` 也只能停在「疑似」；现在按目标 host / port 自动匹配项目资产。
- **渗透回合 `KeyError '"from"'`**：`ROOT_PROTOCOL` 经 `str.format()` 时把 JSON 示例里的 `{"from": ...}` 当作占位符；已改为双花括号并补充渲染验证。
- **报告六、七段为空**：证据路径补齐 `technical_analysis` / `remediation_steps` / `poc_description` / `cwe` / `cve` / `endpoint_source`，统一用 7 段骨架落库。
- **大资产项目创建 422**：`assets` 字段上限由 500 提升到 5000。
- **资产页「加载更多」不符预期**：改为页码窗口 + 上一页 / 下一页；搜索无结果时保留工具栏并提示空态。

---

## [0.2.1] - 2026-10-16

### 新增

- **策略治理层（红线策略）**：`.ravenholt/policy.yaml` 作为 Tier-1 安全网配置面，**fail-closed**——文件缺失、YAML 语法错误或校验失败一律拒绝启动；`rate_limit` / `sandbox` / `kill_switch` / `audit` 四节不允许被关闭。
- **策略审批**：高风险动作进入审批队列，由管理员批准/拒绝；审批记录（挂起 / 批准 / 拒绝 / 模式 / 决策人）可追溯。
- **审计日志**：关键动作与事件的审计追踪（动作、判定、拦截原因、命令原文），独立页面与存储。
- **出口代理**：受控网络出口的配置与管理。
- **源码审计（白盒）通道**：支持上传源码包并走白盒分轨，技能路由与运行时口径随之切换。
- **证据闸与独立验证器**：发现必须携带可复现证据方可置为已确认；验证器以「重放 + 四维差分」独立裁决。
- **一键部署脚本**：`setup.sh` 覆盖 环境检测 → 系统依赖 → 配置初始化 → 数据库 → Python 依赖 → 前端构建 → 沙箱镜像 → 安装后自检，幂等且不覆盖既有配置。

### 变更

- **运行时单轨化到 strix**：退役原生 registry 轨道，改由 vendor 的 strix 运行时驱动；agent 列表改由项目配置决定，不再依赖固定静态角色表。
- **沙箱执行面**：以 docker-py 取代 Go 控制面，统一命令执行与文件管理；新增沙箱镜像工具链适配（PATH 注入、工作目录可配置、容器保活）。
- **前端**：落地页与登录页中文化；导航收敛为 操作台 / 工作项目 / 出口代理 / 策略审批 / 审计日志 / 系统用户 / 系统配置；「快捷导入」并入「系统配置」。
- **文档**：README 重写为完整中文项目文档，包含一键 / 手动 / Docker Compose 三种详细安装方式。

### 移除

- **静态六专家角色表**（cso / cae / cie / cpe / cre / cce）及其人设与知识库——单轨化后已无任何代码读取点。
- **原生 registry 轨道的工具**：`local_shell`、`blackboard`、`knowledge`、`work_project*` 等随该轨道一并删除。
- **过时的项目说明文档**：旧的英文 `README.md` 与 `GUIDE.md` / `GUIDE_zh.md`（内容仍描述已退役的 Blackboard 图与静态专家表）。

### 修复

- **页面改动不生效**：落地页等为**构建期固化**的产物，改源码后必须重新 `npm run build`；已明确该口径并在文档中提示。
- **部署凭据不一致**：旧安装脚本写死的默认管理员/数据库口令，统一改为部署时随机生成且仅打印一次。

---

## 版本号说明

当前 `app.py` 与 `web/package.json` 声明的版本为 `0.2.1`。由于本次为**破坏性重构**（运行时单轨化 + 治理层引入），如需以新版本号发布（例如 `0.3.0`），请同步修改这两处声明后再更新本文件。

"""红线策略（``.ravenholt/policy.yaml``）的 pydantic 模型。

Tier-1 安全网（限速 / kill switch / 沙箱资源限制 / 审计）**不可关闭**，只能调参：
这些节的 ``enabled`` 必须为 true，写成 false 会在校验期直接抛错，
配合 ``core.policy.loader`` 的 fail-closed 语义 → 配置写错即拒绝启动。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    # 与 config.py 的 GlobalConfig 同款：多写字段直接报错，避免拼错的配置被静默忽略
    model_config = ConfigDict(extra="forbid")


def _require_enabled(value: bool, name: str) -> bool:
    if not value:
        raise ValueError(f"{name} 属于 Tier-1 安全网，不可关闭（只能调整其参数）")
    return value


class ScopeConfig(StrictModel):
    """允许的目标范围。列表为空表示不按范围限制（建议仅在受控环境使用）。"""

    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_ports: list[int] = Field(default_factory=list)
    deny_private_ranges: bool = False


class DenylistConfig(StrictModel):
    """明确禁止的动作 / 路径 / 载荷关键词。命中即拒绝并记审计。"""

    actions: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    payload_keywords: list[str] = Field(default_factory=list)


class DosConfig(StrictModel):
    """DoS 判定阈值：命中即拒绝，避免把目标打挂。"""

    max_requests_per_minute_per_target: int = Field(default=120, ge=1)
    # 0 表示不限制并发（面板与 enforcer 都按此语义）
    max_concurrency_per_target: int = Field(default=8, ge=0)
    max_payload_bytes: int = Field(default=1_048_576, ge=1)
    max_requests_total: int = Field(default=0, ge=0)


class ApprovalItem(StrictModel):
    """一条风险审批项 —— 与 ``src-hunt`` 的 ``SKILL.md`` §2「安全红线与授权」逐条对应。

    语义（照 §2 总纲）：**唯一绝对红线是 DoS**（见 :class:`RedlineConfig`）；
    其余动作**默认不做**，用户点头后才发。这里的 ``allow`` 就是"用户是否已点头"：

    - ``allow=False``（默认）→ 命中即进入人工确认队列，逐条批准后才执行；提示词里也会要求
      agent 先说明载荷与影响、等你点头；
    - ``allow=True`` → 该项已获用户放行：闸门不再拦停，提示词改为「**执行前用一句话声明即可，
      不必再等用户确认**」（仍受 scope / denylist / 限速约束）。

    ``signals`` 是**命令文本命中特征**（用户可自定义，大小写不敏感）：裸词按两侧词边界
    匹配、多词特征按左侧词边界匹配；含 ``+`` 的项表示各段须**同时**命中（复合 AND），
    用于表达上下文，例如 ``-x post +/logout`` 只在真的发起登出请求时命中。命中即把该
    命令归入本审批项。空列表 = 不按命令文本判定，只由智能体纪律约束（如「越权写」要看
    业务语义，命令文本判不出来）。
    """

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    allow: bool = False
    signals: list[str] = Field(default_factory=list)


def _default_approvals() -> list[ApprovalItem]:
    """src-hunt 安全红线的审批项默认值。顺序即命令文本的匹配优先级。

    ``description`` 会直接显示给用户（面板与二次确认弹窗），因此只写纯中文说明，
    不带任何出处标记。
    """
    return [
        ApprovalItem(
            key="password_change",
            label="改密码",
            description=(
                "修改目标账号的密码：任何情况下不自己动手，须你明确指名；"
                "改得回就立刻改回原值。"
            ),
            signals=[
                "updatepassword",
                "change_password",
                "changepassword",
                "reset_password",
                "resetpassword",
                "set_password",
                "modifypassword",
                "password/reset",
                "password/change",
            ],
        ),
        ApprovalItem(
            key="destructive",
            label="破坏性操作",
            description=(
                "真资损、批量取数、写死马，以及删除、格式化、改核心配置、关机等"
                "不可逆破坏：默认不做，须你同意。"
            ),
            signals=[
                "rm -rf /",
                "rm -rf /*",
                "rm -rf ~",
                "rm -rf ./*",
                "find / -delete",
                ":(){:|:&};:",
                "mkfs",
                "mke2fs",
                "wipefs",
                "blkdiscard",
                "dd of=/dev/",
                "fdisk",
                "parted",
                "diskpart",
                "iptables -f",
                "iptables -x",
                "iptables -p",
                "systemctl stop",
                "systemctl disable",
                "shutdown",
                "reboot",
                "poweroff",
                "halt",
                "init 0",
                "kill -9 -1",
                "chmod -r 000",
                "drop database",
                "truncate table",
                "mysqldump",
                "pg_dump",
                "mongodump",
                "scp -r /",
            ],
        ),
        ApprovalItem(
            key="payload_exec",
            label="执行型载荷",
            description=(
                "让目标执行我们提供的代码，例如反弹 shell、命令执行、内存马："
                "默认不做；同意前会先说明载荷、会发生什么、副作用影响面、中止与善后。"
            ),
            signals=[
                "msfconsole",
                "msfvenom",
                "meterpreter",
                "--os-shell",
                "--sql-shell",
                "nc -e",
                "/dev/tcp/",
                "reverse shell",
            ],
        ),
        ApprovalItem(
            key="data_mutation",
            label="修改目标数据",
            description=(
                "改绑手机邮箱、改资料、删除、提交、上传落文件等会改变目标状态的写操作："
                "默认不做，须你同意；同意后按最小伤害顺序执行。"
            ),
            signals=[
                "delete from",
                "insert into",
                "alter table",
                "-x put",
                "-x patch",
                "-x delete",
                "--upload-file",
                "--file-write",
                "git push",
            ],
        ),
        ApprovalItem(
            key="logout_revoke",
            label="登出 / 注销 / 吊销",
            description=(
                "调用退出或吊销接口，会让正在使用的登录态失效：默认不做，须你同意。"
            ),
            # 只拦「主动调用」（带 POST 语义）；被动 grep / 读日志提到路径不算。
            signals=[
                "-x post +/logout",
                "-x post +/signout",
                "-x post +/revoke",
                "-x post +revoke_token",
            ],
        ),
        ApprovalItem(
            key="cors",
            label="CORS 跨域探测",
            description="跨域读写探测：默认不挖，只有你点名才做。",
            # 只拦「主动构造跨域请求」（发 Origin / 预检头）；被动读取响应头不再误拦。
            signals=[
                "-h 'origin:",
                '-h "origin:',
                "access-control-request-method",
            ],
        ),
        ApprovalItem(
            key="privilege_write",
            label="越权写",
            description=(
                "写数据以验证越权：默认不做，须你同意；命令文本判不出业务语义，"
                "默认无命中特征，由智能体纪律约束。"
            ),
            signals=[],
        ),
    ]


class RedlineConfig(StrictModel):
    """绝对红线（``src-hunt`` §2.2）：**DoS 同意也不做**。

    命中即硬拒并记审计，**不在控制台提供放行开关**（面板不显示、接口也改不了），
    属 Tier-1 性质；只有命中特征可自定义。

    匹配语义见 :func:`core.policy.action_signals.classify_sandbox_command`：裸词按词边界、
    多词按左侧词边界；且**只对可执行命令生效**，文件正文 / 报告 / 笔记（``scope=content``）
    豁免，避免文档里正当提及工具名被误拒。
    """

    dos_signals: list[str] = Field(default_factory=lambda: [
        "--flood",
        "hping3",
        "slowloris",
        "slowhttptest",
        "t50 ",
        "ab -n 1000000",
        "wrk -t",
        "siege -c",
        "goldeneye",
        "loic ",
        "hoic",
        "ping -f",
    ])


class RateLimitConfig(StrictModel):
    """Tier-1：限速，不可关闭。"""

    enabled: bool = True
    global_per_minute: int = Field(default=600, ge=1)
    per_target_per_minute: int = Field(default=120, ge=1)
    burst: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def _tier1_always_on(self) -> "RateLimitConfig":
        _require_enabled(self.enabled, "rate_limit")
        return self


class SandboxLimitsConfig(StrictModel):
    """Tier-1：沙箱容器资源上限，不可关闭。"""

    enabled: bool = True
    cpu_cores: float = Field(default=2.0, gt=0)
    memory_mb: int = Field(default=2048, ge=64)
    pids_limit: int = Field(default=512, ge=16)

    @model_validator(mode="after")
    def _tier1_always_on(self) -> "SandboxLimitsConfig":
        _require_enabled(self.enabled, "sandbox limits")
        return self


class AuditConfig(StrictModel):
    """Tier-1：审计日志，不可关闭。"""

    enabled: bool = True
    retention_days: int = Field(default=90, ge=1)

    @model_validator(mode="after")
    def _tier1_always_on(self) -> "AuditConfig":
        _require_enabled(self.enabled, "audit")
        return self


class KillSwitchConfig(StrictModel):
    """Tier-1：急停开关，不可关闭。``engaged`` 置位后所有出网动作立即被拒。"""

    enabled: bool = True
    engaged: bool = False
    max_audit_denials_before_engage: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _tier1_always_on(self) -> "KillSwitchConfig":
        _require_enabled(self.enabled, "kill_switch")
        return self


class ReportGateConfig(StrictModel):
    """报告结构门（**可配置**）：finding 离开 draft 前必须达到的最小报告要素。

    src-hunt 的报告口径要求「不能只有一句结论」。这里只校验**现有字段**的完整性；
    src-hunt 7 段里的「复现步骤 / 修复建议」尚未建模，属后续工作。
    """

    enabled: bool = True
    require_asset: bool = True
    min_title_chars: int = Field(default=8, ge=1)
    min_description_chars: int = Field(default=80, ge=0)
    require_impact: bool = True


class PolicyConfig(StrictModel):
    """红线策略根节点。"""

    revision: int = Field(default=1, ge=1)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    denylist: DenylistConfig = Field(default_factory=DenylistConfig)
    dos: DosConfig = Field(default_factory=DosConfig)
    # 风险审批项（src-hunt §2）：默认全部「需人工审批」，控制台逐项放行。
    approvals: list[ApprovalItem] = Field(default_factory=_default_approvals)
    # 绝对红线（src-hunt §2.2）：DoS 硬拒，无放行开关。
    redline: RedlineConfig = Field(default_factory=RedlineConfig)
    # 命中未放行审批项后的挂起时长（秒）：超时按「拒绝」处理，避免无人值守时任务卡死。
    # 0 = 无限等待（需用户自行中断回合）。
    approval_wait_seconds: int = Field(default=600, ge=0)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    sandbox: SandboxLimitsConfig = Field(default_factory=SandboxLimitsConfig)
    kill_switch: KillSwitchConfig = Field(default_factory=KillSwitchConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    report_gate: ReportGateConfig = Field(default_factory=ReportGateConfig)

    @model_validator(mode="after")
    def _unique_approval_keys(self) -> "PolicyConfig":
        keys = [item.key for item in self.approvals]
        if len(set(keys)) != len(keys):
            raise ValueError("approvals 的 key 必须唯一")
        return self


class PolicySnapshotSchema(StrictModel):
    """``GET /api/policy`` 返回体：当前生效策略 + 版本 + 文件路径。"""

    revision: int
    policy_path: str
    policy: PolicyConfig


class ApprovalGateSchema(StrictModel):
    """单个风险审批项的状态（src-hunt §2 的一条例）。

    ``allow=True`` → 已获用户放行，不再逐条确认；``allow=False`` → 命中即进人工确认队列。
    ``signals`` 是该项的命令文本命中特征，随条目一起读写，供面板自定义。
    """

    key: str
    label: str
    description: str
    allow: bool
    signals: list[str]


class PolicyApprovalsSnapshotSchema(StrictModel):
    """``GET`` / ``PATCH /api/policy/actions`` 的返回体：全部审批项 + 版本。"""

    revision: int
    approvals: list[ApprovalGateSchema]


class ApprovalPatchSchema(StrictModel):
    """单个审批项的部分更新：只传需要改的字段，未传的保持不变。"""

    key: str
    allow: bool | None = None
    signals: list[str] | None = None


class UpdatePolicyApprovalsRequest(StrictModel):
    """``PATCH /api/policy/actions`` 请求体；``revision`` 用于乐观并发校验。"""

    revision: int | None = None
    approvals: list[ApprovalPatchSchema]


class UpdatePolicyConfigRequest(StrictModel):
    """``PATCH /api/policy`` 请求体：整份策略的分组部分更新。

    只传需要改动的分组，未传的分组保持不变；``revision`` 用于乐观并发校验。
    ``approvals`` 走独立接口（它按审批项逐条改，不与这里的整组替换混在一起）。
    """

    revision: int | None = None
    scope: ScopeConfig | None = None
    denylist: DenylistConfig | None = None
    dos: DosConfig | None = None
    rate_limit: RateLimitConfig | None = None
    redline: RedlineConfig | None = None
    report_gate: ReportGateConfig | None = None


class KillSwitchRequest(StrictModel):
    """急停开关的置位 / 解除。置位后所有出网动作立即被拒。"""

    engaged: bool

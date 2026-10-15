import type { WorkProjectGraphEdgeCategory } from "../api/contract";
import {
  SANDBOX_CONTAINER_STATUSES,
  SYSTEM_USER_ROLES,
  WORK_PROJECT_ASSET_ORIGINS,
  WORK_PROJECT_ASSET_TYPES,
  WORK_PROJECT_ATTACK_PATH_STATUSES,
  WORK_PROJECT_FINDING_SEVERITIES,
  WORK_PROJECT_FINDING_STATUSES,
  WORK_PROJECT_GRAPH_EDGE_CATEGORIES,
  WORK_PROJECT_GRAPH_EDGE_TYPES,
  WORK_PROJECT_STATUSES,
  WORK_PROJECT_TASK_STATUSES,
  WORK_PROJECT_TYPES,
} from "../api/generated/constants";
import type {
  ConfirmationMode,
  ConfirmationStatus,
  SandboxContainerStatus,
  SystemUserRole,
  WorkProjectAssetOrigin,
  WorkProjectAssetType,
  WorkProjectAttackPathStatus,
  WorkProjectFindingSeverity,
  WorkProjectFindingStatus,
  WorkProjectGraphEdgeType,
  WorkProjectStatus,
  WorkProjectTaskStatus,
  WorkProjectType,
} from "../api/types";

export type SemiTagColor = "amber" | "green" | "red" | "grey" | "blue" | "cyan";

export const SYSTEM_USER_ROLE_LABEL = labelsFromEnum<SystemUserRole>(SYSTEM_USER_ROLES, {
  admin: "管理员",
  user: "普通用户",
});
export const WORK_PROJECT_TYPE_LABEL = labelsFromEnum<WorkProjectType>(WORK_PROJECT_TYPES, {
  penetration_test: "渗透测试",
  source_code_audit: "源码审计",
});
export const WORK_PROJECT_STATUS_LABEL = labelsFromEnum<WorkProjectStatus>(WORK_PROJECT_STATUSES, {
  working: "进行中",
  completed: "已完成",
  canceled: "已取消",
});
export const WORK_PROJECT_TASK_STATUS_LABEL = labelsFromEnum<WorkProjectTaskStatus>(WORK_PROJECT_TASK_STATUSES, {
  todo: "待办",
  in_progress: "进行中",
  blocked: "受阻",
  done: "已完成",
  canceled: "已取消",
});
export const WORK_PROJECT_ASSET_TYPE_LABEL = labelsFromEnum<WorkProjectAssetType>(WORK_PROJECT_ASSET_TYPES, {
  service: "服务",
  domain: "域名",
  network: "网络",
  binary: "二进制",
});
export const WORK_PROJECT_ASSET_ORIGIN_LABEL = labelsFromEnum<WorkProjectAssetOrigin>(WORK_PROJECT_ASSET_ORIGINS, {
  scope: "声明范围",
  discovered: "新发现",
});
export const WORK_PROJECT_FINDING_SEVERITY_LABEL = labelsFromEnum<WorkProjectFindingSeverity>(
  WORK_PROJECT_FINDING_SEVERITIES,
  {
    info: "信息",
    low: "低危",
    medium: "中危",
    high: "高危",
    critical: "严重",
  },
);
export const WORK_PROJECT_FINDING_STATUS_LABEL = labelsFromEnum<WorkProjectFindingStatus>(
  WORK_PROJECT_FINDING_STATUSES,
  {
    suspected: "疑似",
    validated: "已确认",
    false_positive: "误报",
  },
);
export const WORK_PROJECT_GRAPH_EDGE_TYPE_LABEL = labelsFromEnum<WorkProjectGraphEdgeType>(
  WORK_PROJECT_GRAPH_EDGE_TYPES,
  {
    related: "关联",
    resolves_to: "解析到",
    hosts: "承载",
    connects_to: "连接",
    trusts: "信任",
    exploits: "利用",
    pivots_to: "跳板至",
    leads_to: "导致",
  },
);
export const WORK_PROJECT_GRAPH_EDGE_CATEGORY_LABEL = labelsFromEnum<WorkProjectGraphEdgeCategory>(
  WORK_PROJECT_GRAPH_EDGE_CATEGORIES,
  {
    structural: "结构关系",
    offensive: "攻击关系",
  },
);
export const WORK_PROJECT_ATTACK_PATH_STATUS_LABEL = labelsFromEnum<WorkProjectAttackPathStatus>(
  WORK_PROJECT_ATTACK_PATH_STATUSES,
  {
    suspected: "疑似",
    validated: "已确认",
    blocked: "已阻断",
    closed: "已关闭",
  },
);
export const SANDBOX_CONTAINER_STATUS_LABEL = labelsFromEnum<SandboxContainerStatus>(SANDBOX_CONTAINER_STATUSES, {
  created: "已创建",
  running: "运行中",
  stopped: "已停止",
  error: "异常",
});

export const SYSTEM_USER_ROLE_COLOR = colorsFromEnum<SystemUserRole>(SYSTEM_USER_ROLES, {
  admin: "red",
  user: "blue",
});

export const WORK_PROJECT_STATUS_COLOR = colorsFromEnum<WorkProjectStatus>(WORK_PROJECT_STATUSES, {
  working: "amber",
  completed: "green",
  canceled: "grey",
});

export const WORK_PROJECT_TYPE_COLOR = colorsFromEnum<WorkProjectType>(WORK_PROJECT_TYPES, {
  penetration_test: "blue",
  source_code_audit: "cyan",
});

export const WORK_PROJECT_TASK_STATUS_COLOR = colorsFromEnum<WorkProjectTaskStatus>(WORK_PROJECT_TASK_STATUSES, {
  todo: "grey",
  in_progress: "blue",
  blocked: "amber",
  done: "green",
  canceled: "grey",
});

export const WORK_PROJECT_FINDING_SEVERITY_COLOR = colorsFromEnum<WorkProjectFindingSeverity>(WORK_PROJECT_FINDING_SEVERITIES, {
  info: "grey",
  low: "blue",
  medium: "amber",
  high: "red",
  critical: "red",
});

export const WORK_PROJECT_FINDING_STATUS_COLOR = colorsFromEnum<WorkProjectFindingStatus>(WORK_PROJECT_FINDING_STATUSES, {
  suspected: "amber",
  validated: "red",
  false_positive: "grey",
});

export const WORK_PROJECT_ATTACK_PATH_STATUS_COLOR = colorsFromEnum<WorkProjectAttackPathStatus>(WORK_PROJECT_ATTACK_PATH_STATUSES, {
  suspected: "amber",
  validated: "red",
  blocked: "grey",
  closed: "green",
});

export const WORK_PROJECT_ASSET_ORIGIN_COLOR = colorsFromEnum<WorkProjectAssetOrigin>(WORK_PROJECT_ASSET_ORIGINS, {
  scope: "blue",
  discovered: "cyan",
});

export const WORK_PROJECT_GRAPH_EDGE_CATEGORY_COLOR = colorsFromEnum<WorkProjectGraphEdgeCategory>(WORK_PROJECT_GRAPH_EDGE_CATEGORIES, {
  structural: "blue",
  offensive: "red",
});

export const SANDBOX_CONTAINER_STATUS_COLOR = colorsFromEnum<SandboxContainerStatus>(SANDBOX_CONTAINER_STATUSES, {
  created: "blue",
  running: "green",
  stopped: "grey",
  error: "red",
});

function labelsFromEnum<T extends string>(
  values: readonly T[],
  overrides: Partial<Record<T, string>> = {},
): Record<T, string> {
  return Object.fromEntries(values.map((value) => [value, overrides[value] ?? value])) as Record<T, string>;
}

function colorsFromEnum<T extends string>(
  values: readonly T[],
  colors: Partial<Record<T, SemiTagColor>>,
): Record<T, SemiTagColor> {
  return Object.fromEntries(values.map((value) => [value, colors[value] ?? "grey"])) as Record<T, SemiTagColor>;
}

// ── Blackboard labels (manual, not from generated schema) ──
export type BlackboardNodeType = "fact" | "intent" | "hint";
export type BlackboardNodeStatus = "proposed" | "in_progress" | "confirmed" | "rejected" | "superseded";

export const BLACKBOARD_NODE_TYPE_LABEL: Record<BlackboardNodeType, string> = {
  fact: "事实",
  intent: "意图",
  hint: "提示",
};

export const BLACKBOARD_NODE_STATUS_LABEL: Record<BlackboardNodeStatus, string> = {
  proposed: "待定",
  in_progress: "进行中",
  confirmed: "已确认",
  rejected: "已否决",
  superseded: "已被取代",
};

export const BLACKBOARD_NODE_TYPE_COLOR: Record<BlackboardNodeType, SemiTagColor> = {
  fact: "green",
  intent: "blue",
  hint: "amber",
};

export const BLACKBOARD_NODE_STATUS_COLOR: Record<BlackboardNodeStatus, SemiTagColor> = {
  proposed: "grey",
  in_progress: "blue",
  confirmed: "green",
  rejected: "red",
  superseded: "amber",
};

// ── 策略审批 / 审计日志标签（手工维护，生成的 constants 未覆盖这两组枚举） ──
export const POLICY_CONFIRMATION_STATUS_LABEL: Record<ConfirmationStatus, string> = {
  pending: "待确认",
  approved: "已批准",
  rejected: "已拒绝",
};

export const POLICY_CONFIRMATION_STATUS_COLOR: Record<ConfirmationStatus, SemiTagColor> = {
  pending: "amber",
  approved: "green",
  rejected: "grey",
};

export const POLICY_CONFIRMATION_MODE_LABEL: Record<ConfirmationMode, string> = {
  once: "一次性",
  always: "长期信任",
};

export const POLICY_CONFIRMATION_STATUSES: readonly ConfirmationStatus[] = ["pending", "approved", "rejected"];

// 审计事件的动作与分级取自 core/policy/enforcer.py 的 ACTION_CATEGORIES 与审批项 key；
// 未收录的动作直接回显原始标识。
export const AUDIT_ACTION_LABEL: Record<string, string> = {
  "sandbox.exec": "沙箱命令",
  "sandbox.exec.redline.dos": "绝对红线 DoS",
  "sandbox.file.write": "沙箱文件写入",
  "sandbox.file.upload": "沙箱文件上传",
  "sandbox.file.download": "沙箱文件下载",
  "evidence.replay": "证据复放",
  "egress.apply": "出口切换",
  "container.create": "容器创建",
  "policy.update": "策略变更",
};

export const AUDIT_CATEGORY_LABEL: Record<string, string> = {
  read_only: "常规动作",
  sandbox_file: "沙箱内文件",
  redline: "绝对红线",
  // 风险审批项（src-hunt §2）：key 与 core/policy 的 approvals 默认值一致
  password_change: "改密码",
  destructive: "破坏性操作",
  payload_exec: "执行型载荷",
  data_mutation: "修改目标数据",
  logout_revoke: "登出 / 注销 / 吊销",
  cors: "CORS 跨域探测",
  privilege_write: "越权写",
  policy: "策略",
};

export const AUDIT_CATEGORY_COLOR: Record<string, SemiTagColor> = {
  read_only: "grey",
  sandbox_file: "grey",
  redline: "red",
  password_change: "red",
  destructive: "red",
  payload_exec: "red",
  data_mutation: "amber",
  logout_revoke: "amber",
  cors: "blue",
  privilege_write: "amber",
  policy: "cyan",
};

export type AuditDecision = "allow" | "deny";

export const AUDIT_DECISION_LABEL: Record<string, string> = {
  allow: "放行",
  deny: "拦截",
};

export const AUDIT_DECISION_COLOR: Record<string, SemiTagColor> = {
  allow: "green",
  deny: "red",
};

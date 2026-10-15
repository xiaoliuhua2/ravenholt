import { apiGet, apiPatch, apiPost } from "./client";
import type {
  KillSwitchRequest,
  PolicySnapshotResponse,
  UpdatePolicyConfigRequest,
} from "./types";

const POLICY_PATH = "/api/policy";

/** 读取完整策略快照（所有登录用户可用）。 */
export function getPolicyConfig() {
  return apiGet<PolicySnapshotResponse>(POLICY_PATH);
}

/** 提交分组配置变更：写回策略文件并即时生效；revision 用于乐观并发校验。 */
export function updatePolicyConfig(payload: UpdatePolicyConfigRequest) {
  return apiPatch<PolicySnapshotResponse>(POLICY_PATH, payload);
}

/** 置位 / 解除急停开关；置位后所有出网动作立即被拒。 */
export function setKillSwitch(payload: KillSwitchRequest) {
  return apiPost<PolicySnapshotResponse>(`${POLICY_PATH}/kill-switch`, payload);
}

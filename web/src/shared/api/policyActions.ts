import { apiGet, apiPatch } from "./client";
import type { PolicyActionsSnapshotResponse, UpdatePolicyActionsRequest } from "./types";

const POLICY_ACTIONS_PATH = "/api/policy/actions";

/** 读取全部风险审批项的放行状态与命中特征（所有登录用户可用）。 */
export function getPolicyActions() {
  return apiGet<PolicyActionsSnapshotResponse>(POLICY_ACTIONS_PATH);
}

/** 提交审批项变更（放行 / 命中特征）：写回策略文件并即时生效；revision 用于乐观并发校验。 */
export function updatePolicyActions(payload: UpdatePolicyActionsRequest) {
  return apiPatch<PolicyActionsSnapshotResponse>(POLICY_ACTIONS_PATH, payload);
}

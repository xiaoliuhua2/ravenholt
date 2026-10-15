import { apiDelete, apiGet, apiPost } from "./client";
import { buildQuery } from "./query";
import type {
  ApprovePolicyConfirmationResponse,
  CommonResponsePayload,
  DecidePolicyConfirmationRequest,
  QueryPolicyConfirmationsParams,
  QueryPolicyConfirmationsResponse,
  RejectPolicyConfirmationResponse,
  RevokePolicyConfirmationResponse,
} from "./types";

const POLICY_CONFIRMATIONS_PATH = "/api/policy/confirmations";

export function queryPolicyConfirmations(params: QueryPolicyConfirmationsParams) {
  return apiGet<QueryPolicyConfirmationsResponse>(`${POLICY_CONFIRMATIONS_PATH}${buildQuery(params)}`);
}

export function approvePolicyConfirmation(id: number, payload: DecidePolicyConfirmationRequest) {
  return apiPost<ApprovePolicyConfirmationResponse>(`${POLICY_CONFIRMATIONS_PATH}/${id}/approve`, payload);
}

export function rejectPolicyConfirmation(id: number, payload: DecidePolicyConfirmationRequest) {
  return apiPost<RejectPolicyConfirmationResponse>(`${POLICY_CONFIRMATIONS_PATH}/${id}/reject`, payload);
}

export function revokePolicyConfirmation(id: number) {
  return apiPost<RevokePolicyConfirmationResponse>(`${POLICY_CONFIRMATIONS_PATH}/${id}/revoke`);
}

/** 删除一条审批记录（待办 / 已决 / 已撤销都能删；审计日志里的痕迹不受影响）。 */
export function deletePolicyConfirmation(id: number) {
  return apiDelete<CommonResponsePayload>(`${POLICY_CONFIRMATIONS_PATH}/${id}`);
}

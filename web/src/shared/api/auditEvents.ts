import { apiGet, apiPost } from "./client";
import { buildQuery } from "./query";
import type {
  DeleteAuditEventsRequest,
  DeleteAuditEventsResponse,
  PurgeAuditEventsRequest,
  PurgeAuditEventsResponse,
  QueryAuditEventsParams,
  QueryAuditEventsResponse,
} from "./types";

const AUDIT_EVENTS_PATH = "/api/audit-events";

export function queryAuditEvents(params: QueryAuditEventsParams) {
  return apiGet<QueryAuditEventsResponse>(`${AUDIT_EVENTS_PATH}${buildQuery(params)}`);
}

export function deleteAuditEvents(ids: DeleteAuditEventsRequest["ids"]) {
  return apiPost<DeleteAuditEventsResponse>(`${AUDIT_EVENTS_PATH}/delete`, { ids });
}

/** 按筛选条件批量删除（条件全空 = 清空全部）。 */
export function purgeAuditEvents(params: PurgeAuditEventsRequest = {}) {
  return apiPost<PurgeAuditEventsResponse>(`${AUDIT_EVENTS_PATH}/purge`, params);
}

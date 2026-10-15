import { apiDelete, apiForm, apiGet, apiPatch, apiPost } from "./client";
import { buildQuery } from "./query";
import type {
  BlackboardProjectPathParams,
  CancelWorkProjectPathParams,
  CancelWorkProjectResponse,
  CreateWorkProjectRequest,
  CreateWorkProjectResponse,
  CreateWorkProjectSessionResponse,
  DeleteWorkProjectSessionResponse,
  DeleteWorkProjectResponse,
  GetBlackboardSnapshotResponse,
  GetWorkProjectFindingEvidenceResponse,
  GetWorkProjectRecordSnapshotResponse,
  ListWorkProjectSessionsResponse,
  QueryWorkProjectsParams,
  QueryWorkProjectsResponse,
  RetryWorkProjectPathParams,
  RetryWorkProjectResponse,
  UpdateWorkProjectMetadataRequest,
  UpdateWorkProjectMetadataResponse,
  UploadWorkProjectSourceResponse,
  WorkProjectPathParams,
} from "./types";

const WORK_PROJECTS_PATH = "/api/work-projects";

export function queryWorkProjects(params: QueryWorkProjectsParams) {
  return apiGet<QueryWorkProjectsResponse>(`${WORK_PROJECTS_PATH}${buildQuery(params)}`);
}

export function createWorkProject(payload: CreateWorkProjectRequest) {
  return apiPost<CreateWorkProjectResponse>(WORK_PROJECTS_PATH, payload);
}

/** 上传源码归档（zip / tar）；解压后的 server_path 直接用作 binary 资产的 path。 */
export function uploadWorkProjectSource(file: File) {
  const form = new FormData();
  form.append("files", file);
  return apiForm<UploadWorkProjectSourceResponse>(`${WORK_PROJECTS_PATH}/source-uploads`, form);
}

export function getWorkProjectRecordSnapshot(id: WorkProjectPathParams["id"]) {
  return apiGet<GetWorkProjectRecordSnapshotResponse>(`${WORK_PROJECTS_PATH}/${id}/record-snapshot`);
}

export function getWorkProjectFindingEvidence(id: WorkProjectPathParams["id"], findingId: number) {
  return apiGet<GetWorkProjectFindingEvidenceResponse>(
    `${WORK_PROJECTS_PATH}/${id}/findings/${findingId}/evidence`,
  );
}

export function updateWorkProjectMetadata(id: WorkProjectPathParams["id"], payload: UpdateWorkProjectMetadataRequest) {
  return apiPatch<UpdateWorkProjectMetadataResponse>(`${WORK_PROJECTS_PATH}/${id}/metadata`, payload);
}

export function listWorkProjectSessions(id: WorkProjectPathParams["id"]) {
  return apiGet<ListWorkProjectSessionsResponse>(`${WORK_PROJECTS_PATH}/${id}/sessions`);
}

export function createWorkProjectSession(id: WorkProjectPathParams["id"]) {
  return apiPost<CreateWorkProjectSessionResponse>(`${WORK_PROJECTS_PATH}/${id}/sessions`);
}

export function deleteWorkProjectSession(id: WorkProjectPathParams["id"], sessionId: string) {
  return apiDelete<DeleteWorkProjectSessionResponse>(
    `${WORK_PROJECTS_PATH}/${id}/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export function cancelWorkProject(id: CancelWorkProjectPathParams["id"]) {
  return apiPost<CancelWorkProjectResponse>(`${WORK_PROJECTS_PATH}/${id}/cancel`);
}

export function retryWorkProject(id: RetryWorkProjectPathParams["id"]) {
  return apiPost<RetryWorkProjectResponse>(`${WORK_PROJECTS_PATH}/${id}/retry`);
}

export function deleteWorkProject(id: WorkProjectPathParams["id"]) {
  return apiDelete<DeleteWorkProjectResponse>(`${WORK_PROJECTS_PATH}/${id}`);
}

// ── Blackboard ──
const BLACKBOARD_PATH = "/api/blackboard";

export function getBlackboardSnapshot(id: BlackboardProjectPathParams["project_id"]) {
  return apiGet<GetBlackboardSnapshotResponse>(`${BLACKBOARD_PATH}/${id}`);
}

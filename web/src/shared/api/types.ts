import type { components, paths } from "./generated/schema";

type JsonRequestBody<Operation> = Operation extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? Body
  : never;

type MultipartRequestBody<Operation> = Operation extends {
  requestBody: { content: { "multipart/form-data": infer Body } };
}
  ? Body
  : never;

type JsonResponse<Operation> = Operation extends {
  responses: { 200: { content: { "application/json": infer Response } } };
}
  ? Response
  : never;

type QueryParameters<Operation> = Operation extends { parameters: { query?: infer Query } } ? Query : never;
type PathParameters<Operation> = Operation extends { parameters: { path?: infer Params } } ? Params : never;

export type CommonResponsePayload = components["schemas"]["CommonResponse"];

export type LoginRequest = JsonRequestBody<paths["/api/system-users/login"]["post"]>;
export type LoginResponse = JsonResponse<paths["/api/system-users/login"]["post"]>;

export type QuerySystemUsersParams = QueryParameters<paths["/api/system-users"]["get"]>;
export type QuerySystemUsersResponse = JsonResponse<paths["/api/system-users"]["get"]>;
export type QuerySystemUsersData = NonNullable<QuerySystemUsersResponse["data"]>;
export type SystemUser = QuerySystemUsersData["items"][number];
export type SystemUserRole = components["schemas"]["SystemUserRole"];

export type CreateSystemUserRequest = JsonRequestBody<paths["/api/system-users"]["post"]>;
export type CreateSystemUserResponse = JsonResponse<paths["/api/system-users"]["post"]>;

export type SystemUserPathParams = PathParameters<paths["/api/system-users/{id}"]["patch"]>;
export type UpdateSystemUserRequest = JsonRequestBody<paths["/api/system-users/{id}"]["patch"]>;
export type UpdateSystemUserResponse = JsonResponse<paths["/api/system-users/{id}"]["patch"]>;
export type DeleteSystemUserResponse = JsonResponse<paths["/api/system-users/{id}"]["delete"]>;

export type QueryManagedHostsParams = QueryParameters<paths["/api/hosts"]["get"]>;
export type QueryManagedHostsResponse = JsonResponse<paths["/api/hosts"]["get"]>;
export type QueryManagedHostsData = NonNullable<QueryManagedHostsResponse["data"]>;
export type ManagedHost = QueryManagedHostsData["items"][number];

export type CreateManagedHostRequest = JsonRequestBody<paths["/api/hosts"]["post"]>;
export type CreateManagedHostResponse = JsonResponse<paths["/api/hosts"]["post"]>;

export type ManagedHostPathParams = PathParameters<paths["/api/hosts/{id}"]["patch"]>;
export type UpdateManagedHostRequest = JsonRequestBody<paths["/api/hosts/{id}"]["patch"]>;
export type UpdateManagedHostResponse = JsonResponse<paths["/api/hosts/{id}"]["patch"]>;
export type DeleteManagedHostResponse = JsonResponse<paths["/api/hosts/{id}"]["delete"]>;

export type DeleteManagedHostImageRequest = JsonRequestBody<paths["/api/hosts/{id}/images/remove"]["post"]>;

export type QueryEgressProxiesParams = QueryParameters<paths["/api/egress-proxies"]["get"]>;
export type QueryEgressProxiesResponse = JsonResponse<paths["/api/egress-proxies"]["get"]>;
export type QueryEgressProxiesData = NonNullable<QueryEgressProxiesResponse["data"]>;
export type EgressProxy = QueryEgressProxiesData["items"][number];
export type EgressProxyType = components["schemas"]["EgressProxyType"];

export type CreateEgressProxyRequest = JsonRequestBody<paths["/api/egress-proxies"]["post"]>;
export type CreateEgressProxyResponse = JsonResponse<paths["/api/egress-proxies"]["post"]>;

export type EgressProxyPathParams = PathParameters<paths["/api/egress-proxies/{id}"]["patch"]>;
export type UpdateEgressProxyRequest = JsonRequestBody<paths["/api/egress-proxies/{id}"]["patch"]>;
export type UpdateEgressProxyResponse = JsonResponse<paths["/api/egress-proxies/{id}"]["patch"]>;
export type DeleteEgressProxyResponse = JsonResponse<paths["/api/egress-proxies/{id}"]["delete"]>;
export type TestEgressProxyPathParams = PathParameters<paths["/api/egress-proxies/{id}/test"]["post"]>;
export type TestEgressProxyResponse = JsonResponse<paths["/api/egress-proxies/{id}/test"]["post"]>;

export type InstanceConfig = components["schemas"]["InstanceConfigSchema"];
export type AgentConfig = components["schemas"]["AgentConfig"];
export type AgentPoolConfig = components["schemas"]["AgentPoolConfig"];
export type AgentRuntimeConfig = components["schemas"]["AgentRuntimeConfig"];
export type IntegrationsConfig = components["schemas"]["IntegrationsConfig"];
export type GetInstanceConfigResponse = JsonResponse<paths["/api/system-config/instance"]["get"]>;
export type UpdateInstanceConfigRequest = JsonRequestBody<paths["/api/system-config/instance"]["patch"]>;
export type UpdateInstanceConfigResponse = JsonResponse<paths["/api/system-config/instance"]["patch"]>;
export type FetchUpstreamModelsRequest = JsonRequestBody<paths["/api/system-config/upstream-models"]["post"]>;
export type FetchUpstreamModelsResponse = JsonResponse<paths["/api/system-config/upstream-models"]["post"]>;

export type QuerySandboxImagesParams = QueryParameters<paths["/api/sandbox-images"]["get"]>;
export type QuerySandboxImagesResponse = JsonResponse<paths["/api/sandbox-images"]["get"]>;
export type QuerySandboxImagesData = NonNullable<QuerySandboxImagesResponse["data"]>;
export type SandboxImage = QuerySandboxImagesData["items"][number];

export type CreateSandboxImageRequest = JsonRequestBody<paths["/api/sandbox-images"]["post"]>;
export type CreateSandboxImageResponse = JsonResponse<paths["/api/sandbox-images"]["post"]>;

export type SandboxImagePathParams = PathParameters<paths["/api/sandbox-images/{id}"]["delete"]>;
export type DeleteSandboxImageResponse = JsonResponse<paths["/api/sandbox-images/{id}"]["delete"]>;

export type ListManagedHostImagesResponse = JsonResponse<paths["/api/hosts/{id}/images"]["get"]>;
export type ManagedHostImage = NonNullable<ListManagedHostImagesResponse["data"]>["items"][number];
export type PullManagedHostImagesRequest = JsonRequestBody<paths["/api/hosts/{id}/images/pull"]["post"]>;
export type PullManagedHostImagesResponse = JsonResponse<paths["/api/hosts/{id}/images/pull"]["post"]>;

export type QuerySandboxContainersParams = QueryParameters<paths["/api/sandbox-containers"]["get"]>;
export type QuerySandboxContainersResponse = JsonResponse<paths["/api/sandbox-containers"]["get"]>;
export type QuerySandboxContainersData = NonNullable<QuerySandboxContainersResponse["data"]>;
export type SandboxContainer = QuerySandboxContainersData["items"][number];
export type QueryAvailableSandboxContainersParams = QueryParameters<paths["/api/sandbox-containers/available"]["get"]>;
export type QueryAvailableSandboxContainersResponse = JsonResponse<paths["/api/sandbox-containers/available"]["get"]>;
export type SandboxContainerStatus = components["schemas"]["SandboxContainerStatus"];
export type SandboxContainerSource = components["schemas"]["SandboxContainerSource"];
export type SandboxContainerEgressMode = components["schemas"]["SandboxContainerEgressMode"];
export type SandboxContainerPortMapping = components["schemas"]["SandboxContainerPortMapping"];

export type CreateSandboxContainerRequest = JsonRequestBody<paths["/api/sandbox-containers"]["post"]>;
export type CreateSandboxContainerResponse = JsonResponse<paths["/api/sandbox-containers"]["post"]>;

export type SandboxContainerPathParams = PathParameters<paths["/api/sandbox-containers/{id}"]["delete"]>;
export type DeleteSandboxContainerResponse = JsonResponse<paths["/api/sandbox-containers/{id}"]["delete"]>;
export type StartSandboxContainerPathParams = PathParameters<paths["/api/sandbox-containers/{id}/start"]["post"]>;
export type StartSandboxContainerResponse = JsonResponse<paths["/api/sandbox-containers/{id}/start"]["post"]>;
export type StopSandboxContainerPathParams = PathParameters<paths["/api/sandbox-containers/{id}/stop"]["post"]>;
export type StopSandboxContainerResponse = JsonResponse<paths["/api/sandbox-containers/{id}/stop"]["post"]>;
export type UpdateSandboxContainerEgressPathParams = PathParameters<paths["/api/sandbox-containers/{id}/egress"]["patch"]>;
export type UpdateSandboxContainerEgressRequest = JsonRequestBody<paths["/api/sandbox-containers/{id}/egress"]["patch"]>;
export type UpdateSandboxContainerEgressResponse = JsonResponse<paths["/api/sandbox-containers/{id}/egress"]["patch"]>;

export type ListContainerFilesParams = QueryParameters<paths["/api/sandbox-containers/{id}/files"]["get"]>;
export type ListContainerFilesResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files"]["get"]>;
export type ContainerFileInfo = components["schemas"]["ContainerFileInfo"];
export type ContainerFileType = components["schemas"]["ContainerFileType"];

export type ReadContainerFileParams = QueryParameters<paths["/api/sandbox-containers/{id}/files/read"]["get"]>;
export type ReadContainerFileResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/read"]["get"]>;

export type ContainerFileWriteRequest = JsonRequestBody<paths["/api/sandbox-containers/{id}/files/write"]["post"]>;
export type ContainerFileWriteResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/write"]["post"]>;
export type ContainerFileUploadRequest = MultipartRequestBody<paths["/api/sandbox-containers/{id}/files/upload"]["post"]>;
export type ContainerFileUploadResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/upload"]["post"]>;
export type DownloadContainerFilesParams = QueryParameters<paths["/api/sandbox-containers/{id}/files/download"]["get"]>;
export type ContainerFileCopyRequest = JsonRequestBody<paths["/api/sandbox-containers/{id}/files/copy"]["post"]>;
export type ContainerFileCopyResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/copy"]["post"]>;
export type ContainerFileMoveRequest = JsonRequestBody<paths["/api/sandbox-containers/{id}/files/move"]["post"]>;
export type ContainerFileMoveResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/move"]["post"]>;
export type ContainerFileDeleteRequest = JsonRequestBody<paths["/api/sandbox-containers/{id}/files/delete"]["post"]>;
export type ContainerFileDeleteResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/delete"]["post"]>;
export type ContainerFileMkdirRequest = JsonRequestBody<paths["/api/sandbox-containers/{id}/files/mkdir"]["post"]>;
export type ContainerFileMkdirResponse = JsonResponse<paths["/api/sandbox-containers/{id}/files/mkdir"]["post"]>;

export type QueryWorkProjectsParams = QueryParameters<paths["/api/work-projects"]["get"]>;
export type QueryWorkProjectsResponse = JsonResponse<paths["/api/work-projects"]["get"]>;
export type QueryWorkProjectsData = NonNullable<QueryWorkProjectsResponse["data"]>;
export type WorkProject = QueryWorkProjectsData["items"][number];
export type WorkProjectStatus = components["schemas"]["WorkProjectStatus"];
export type WorkProjectType = components["schemas"]["WorkProjectType"];
export type WorkProjectTaskStatus = components["schemas"]["WorkProjectTaskStatus"];
export type WorkProjectAgentSummary = components["schemas"]["WorkProjectAgentSummarySchema"];
export type WorkProjectAsset = components["schemas"]["WorkProjectAssetSchema"];
export type WorkProjectAssetExtra = components["schemas"]["WorkProjectAssetExtraSchema"];
export type WorkProjectAssetRequest = components["schemas"]["WorkProjectAssetRequest"];
export type WorkProjectAssetType = components["schemas"]["WorkProjectAssetType"];
export type WorkProjectAssetOrigin = components["schemas"]["WorkProjectAssetOrigin"];
export type WorkProjectFinding = components["schemas"]["WorkProjectFindingSchema"];
export type WorkProjectFindingSeverity = components["schemas"]["WorkProjectFindingSeverity"];
export type WorkProjectFindingStatus = components["schemas"]["WorkProjectFindingStatus"];
export type WorkProjectGraphEdge = components["schemas"]["WorkProjectGraphEdgeSchema"];
export type WorkProjectGraphEdgeType = components["schemas"]["WorkProjectGraphEdgeType"];
export type WorkProjectGraphSnapshot = components["schemas"]["WorkProjectGraphSnapshotSchema"];
export type WorkProjectAttackPath = components["schemas"]["WorkProjectAttackPathSchema"];
export type WorkProjectAttackPathStatus = components["schemas"]["WorkProjectAttackPathStatus"];
export type WorkProjectAttackPathStep = components["schemas"]["WorkProjectAttackPathStepSchema"];
export type WorkProjectRecords = components["schemas"]["WorkProjectRecordsSchema"];
export type WorkProjectRecordSnapshot = components["schemas"]["WorkProjectRecordSnapshotSchema"];

export type CreateWorkProjectRequest = JsonRequestBody<paths["/api/work-projects"]["post"]>;
export type CreateWorkProjectResponse = JsonResponse<paths["/api/work-projects"]["post"]>;

export type WorkProjectPathParams = PathParameters<paths["/api/work-projects/{id}/record-snapshot"]["get"]>;
export type UpdateWorkProjectMetadataRequest = JsonRequestBody<paths["/api/work-projects/{id}/metadata"]["patch"]>;
export type UpdateWorkProjectMetadataResponse = JsonResponse<paths["/api/work-projects/{id}/metadata"]["patch"]>;
export type DeleteWorkProjectResponse = JsonResponse<paths["/api/work-projects/{id}"]["delete"]>;
export type CancelWorkProjectPathParams = PathParameters<paths["/api/work-projects/{id}/cancel"]["post"]>;
export type CancelWorkProjectResponse = JsonResponse<paths["/api/work-projects/{id}/cancel"]["post"]>;
export type RetryWorkProjectPathParams = PathParameters<paths["/api/work-projects/{id}/retry"]["post"]>;
export type RetryWorkProjectResponse = JsonResponse<paths["/api/work-projects/{id}/retry"]["post"]>;
export type ListWorkProjectSessionsResponse = JsonResponse<paths["/api/work-projects/{id}/sessions"]["get"]>;
export type CreateWorkProjectSessionResponse = JsonResponse<paths["/api/work-projects/{id}/sessions"]["post"]>;
export type DeleteWorkProjectSessionResponse = JsonResponse<paths["/api/work-projects/{id}/sessions/{session_id}"]["delete"]>;
export type GetWorkProjectRecordSnapshotResponse = JsonResponse<paths["/api/work-projects/{id}/record-snapshot"]["get"]>;

// 源码包上传（multipart）：解压后返回的 server_path 直接作为 binary 资产的 path。
export type UploadWorkProjectSourceRequest = MultipartRequestBody<paths["/api/work-projects/source-uploads"]["post"]>;
export type UploadWorkProjectSourceResponse = JsonResponse<paths["/api/work-projects/source-uploads"]["post"]>;
export type WorkProjectSourceUpload = NonNullable<UploadWorkProjectSourceResponse["data"]>;

// ── Blackboard (manual types, not from generated schema) ──
export type BlackboardNodeType = "fact" | "intent" | "hint";
export type BlackboardNodeStatus = "proposed" | "in_progress" | "confirmed" | "rejected" | "superseded";

export interface BlackboardNode {
  id: number;
  project_id: number;
  node_type: BlackboardNodeType;
  status: BlackboardNodeStatus;
  description: string;
  parent_ids: string;
  creator_agent_code: string;
  session_id: string;
  confidence: number;
  extra: string;
  created_at: string;
  updated_at: string;
}

export interface BlackboardSnapshot {
  project_id: number;
  nodes: BlackboardNode[];
  total_count: number;
}

export type GetBlackboardSnapshotResponse = { code: number; message: string; data?: BlackboardSnapshot | null };
export type BlackboardProjectPathParams = { project_id: number };

// ── 发现证据包（手写类型：可重放的完整请求 + baseline/probe 响应） ──
export interface WorkProjectFindingEvidence {
  finding_id: number;
  evidence_id: number;
  target: string;
  method: string;
  url: string;
  request_headers: Record<string, string>;
  request_body: string;
  baseline_status: number;
  baseline_body: string;
  probe_status: number;
  probe_body: string;
  diff: Record<string, unknown>;
  verdict: string;
  verifier_note: string;
  captured_at: string;
}

export type GetWorkProjectFindingEvidenceResponse = {
  code: number;
  message: string;
  data?: WorkProjectFindingEvidence | null;
};

export type AgentSessionSummary = components["schemas"]["AgentSessionSummarySchema"];
export type SessionType = components["schemas"]["SessionType"];

export type AgentInfo = components["schemas"]["AgentInfoSchema"];
export type ListAgentsResponse = JsonResponse<paths["/api/agents"]["get"]>;
export type ListAgentsData = NonNullable<ListAgentsResponse["data"]>;

export type ListAgentSessionsResponse = JsonResponse<paths["/api/agent-sessions"]["get"]>;
export type ListAgentSessionsData = NonNullable<ListAgentSessionsResponse["data"]>;

export type AgentTurnData = components["schemas"]["AgentTurnResponse"];
export type StrixTurnRequest = JsonRequestBody<paths["/api/agent-sessions/strix-turns"]["post"]>;
export type CreateAgentSessionStrixTurnResponse = JsonResponse<paths["/api/agent-sessions/strix-turns"]["post"]>;
export type SubmitAgentSessionStrixTurnResponse = JsonResponse<paths["/api/agent-sessions/{session_id}/strix-turn"]["post"]>;
export type InterruptAgentSessionResponse = JsonResponse<paths["/api/agent-sessions/{session_id}/interrupt"]["post"]>;
export type CancelAllAgentSessionTasksResponse = JsonResponse<paths["/api/agent-sessions/{session_id}/cancel-all"]["post"]>;

export type ListAgentEventsResponse = JsonResponse<paths["/api/agent-sessions/{session_id}/events"]["get"]>;
export type ListAgentEventsData = NonNullable<ListAgentEventsResponse["data"]>;
export type UpdateAgentSessionTitleRequest = JsonRequestBody<paths["/api/agent-sessions/{session_id}/title"]["patch"]>;
export type UpdateAgentSessionTitleResponse = JsonResponse<paths["/api/agent-sessions/{session_id}/title"]["patch"]>;
export type DeleteAgentSessionResponse = JsonResponse<paths["/api/agent-sessions/{session_id}"]["delete"]>;

export type UserMessageEvent = components["schemas"]["UserMessageEvent"];
export type TurnBoundaryEvent = components["schemas"]["TurnBoundaryEvent"];
export type TextDeltaEvent = components["schemas"]["TextDeltaEvent"];
export type TextCompleteEvent = components["schemas"]["TextCompleteEvent"];
export type ThinkingDeltaEvent = components["schemas"]["ThinkingDeltaEvent"];
export type ThinkingCompleteEvent = components["schemas"]["ThinkingCompleteEvent"];
export type ToolCallEvent = components["schemas"]["ToolCallEvent"];
export type ToolResultEvent = components["schemas"]["ToolResultEvent"];
export type SubagentTaskEvent = components["schemas"]["SubagentTaskEvent"];
export type SandboxEvent = components["schemas"]["SandboxEvent"];
export type SandboxPhase = components["schemas"]["SandboxPhaseSchema"];
export type ApprovalEvent = components["schemas"]["ApprovalEvent"];
export type ApprovalPhase = components["schemas"]["ApprovalPhaseSchema"];
export type AgentSubordinateStatus = components["schemas"]["AgentSubordinateStatus"];
export type ErrorEvent = components["schemas"]["ErrorEvent"];
export type DoneEvent = components["schemas"]["DoneEvent"];
export type RunStateEvent = components["schemas"]["RunStateEvent"];
export type AgentInputPart = components["schemas"]["AgentTextInputPart"] | components["schemas"]["AgentImageInputPart"];
export type AgentTextInputPart = components["schemas"]["AgentTextInputPart"];
export type AgentImageInputPart = components["schemas"]["AgentImageInputPart"];

// ── 策略审批 / 审计日志 ──
export type ConfirmationStatus = components["schemas"]["ConfirmationStatus"];
export type ConfirmationMode = components["schemas"]["ConfirmationMode"];
export type PolicyConfirmation = components["schemas"]["PolicyConfirmationSchema"];
export type QueryPolicyConfirmationsParams = QueryParameters<paths["/api/policy/confirmations"]["get"]>;
export type QueryPolicyConfirmationsResponse = JsonResponse<paths["/api/policy/confirmations"]["get"]>;
export type DecidePolicyConfirmationRequest = JsonRequestBody<paths["/api/policy/confirmations/{id}/approve"]["post"]>;
export type ApprovePolicyConfirmationResponse = JsonResponse<paths["/api/policy/confirmations/{id}/approve"]["post"]>;
export type RejectPolicyConfirmationResponse = JsonResponse<paths["/api/policy/confirmations/{id}/reject"]["post"]>;
export type RevokePolicyConfirmationResponse = JsonResponse<paths["/api/policy/confirmations/{id}/revoke"]["post"]>;

export type PolicyActionsSnapshotResponse = JsonResponse<paths["/api/policy/actions"]["get"]>;
export type PolicyApprovalGates = NonNullable<PolicyActionsSnapshotResponse["data"]>["approvals"];
export type PolicyApprovalGate = PolicyApprovalGates[number];
export type UpdatePolicyActionsRequest = JsonRequestBody<paths["/api/policy/actions"]["patch"]>;

export type PolicySnapshotResponse = JsonResponse<paths["/api/policy"]["get"]>;
export type PolicyConfig = NonNullable<PolicySnapshotResponse["data"]>["policy"];
export type UpdatePolicyConfigRequest = JsonRequestBody<paths["/api/policy"]["patch"]>;
export type KillSwitchRequest = JsonRequestBody<paths["/api/policy/kill-switch"]["post"]>;

export type AuditEvent = components["schemas"]["AuditEventSchema"];
export type QueryAuditEventsParams = QueryParameters<paths["/api/audit-events"]["get"]>;
export type QueryAuditEventsResponse = JsonResponse<paths["/api/audit-events"]["get"]>;
export type QueryAuditEventsData = NonNullable<QueryAuditEventsResponse["data"]>;

// ── 审计事件删除（手写类型：新端点未进 openapi.json） ──
export type DeleteAuditEventsRequest = { ids: number[] };
export type DeleteAuditEventsResponse = {
  code: number;
  message: string;
  data?: { deleted: number } | null;
};
export type PurgeAuditEventsRequest = { action?: string; decision?: string; keyword?: string };
export type PurgeAuditEventsResponse = {
  code: number;
  message: string;
  data?: { deleted: number } | null;
};

export type AgentContentEvent = ListAgentEventsData["items"][number];
export type AgentStreamEvent = UserMessageEvent | TurnBoundaryEvent | RunStateEvent | TextDeltaEvent | TextCompleteEvent
  | ThinkingDeltaEvent | ThinkingCompleteEvent | ToolCallEvent | ToolResultEvent
  | SubagentTaskEvent | SandboxEvent | ApprovalEvent | DoneEvent | ErrorEvent;

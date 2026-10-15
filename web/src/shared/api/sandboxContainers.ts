import { apiBlob, apiForm, apiGet, apiPost } from "./client";
import { SANDBOX_CONTAINER_STATUS } from "./generated/constants";
import { getStoredAccessToken } from "../auth/session";
import { buildQuery } from "./query";
import type {
  ContainerFileCopyRequest,
  ContainerFileCopyResponse,
  ContainerFileDeleteRequest,
  ContainerFileDeleteResponse,
  ContainerFileMkdirRequest,
  ContainerFileMkdirResponse,
  ContainerFileMoveRequest,
  ContainerFileMoveResponse,
  ContainerFileUploadRequest,
  ContainerFileUploadResponse,
  ContainerFileWriteRequest,
  ContainerFileWriteResponse,
  ListContainerFilesParams,
  ListContainerFilesResponse,
  DownloadContainerFilesParams,
  QueryAvailableSandboxContainersParams,
  QueryAvailableSandboxContainersResponse,
  ReadContainerFileParams,
  ReadContainerFileResponse,
  SandboxContainer,
} from "./types";

const SANDBOX_CONTAINERS_PATH = "/api/sandbox-containers";

export function queryAvailableSandboxContainers(params: QueryAvailableSandboxContainersParams) {
  return apiGet<QueryAvailableSandboxContainersResponse>(`${SANDBOX_CONTAINERS_PATH}/available${buildQuery(params)}`);
}

// ── Caido 抓包入口 ─────────────────────────────────────────────────────────

// 沙箱容器内 Caido 侧车端口，与后端 service/sandbox/caido.py 的 CAIDO_CONTAINER_PORT 对齐
const SANDBOX_CAIDO_CONTAINER_PORT = 48080;

export function containerCaidoHostPort(container: SandboxContainer) {
  const mapping = container.port_mappings.find(
    (item) => item.container_port === SANDBOX_CAIDO_CONTAINER_PORT && item.protocol === "tcp",
  );
  return mapping?.host_port ?? 0;
}

export function canOpenContainerCaido(container: SandboxContainer) {
  return Boolean(container.status === SANDBOX_CONTAINER_STATUS.RUNNING && containerCaidoHostPort(container) > 0);
}

/**
 * Caido 由后端按路径前缀反代（侧车端口只发布在宿主回环地址上）。
 * 首屏用 ?token= 换成 HttpOnly Cookie，之后由 Caido 前端自行用相对路径发起请求。
 * 入口必须带结尾斜杠，否则相对路径会退化到上一层前缀。
 */
export function buildContainerCaidoUrl(container: SandboxContainer) {
  if (!canOpenContainerCaido(container)) {
    throw new Error("container caido port is not ready");
  }

  const token = getStoredAccessToken();
  if (!token) throw new Error("missing access token");

  const path = `${SANDBOX_CONTAINERS_PATH}/${container.id}/caido/?token=${encodeURIComponent(token)}`;
  return `${window.location.origin}${path}`;
}


// ── container file operations ──────────────────────────────────────────────

export function listContainerFiles(id: number, params: ListContainerFilesParams) {
  return apiGet<ListContainerFilesResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files${buildQuery(params)}`);
}

export function readContainerFile(id: number, params: ReadContainerFileParams) {
  return apiGet<ReadContainerFileResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/read${buildQuery(params)}`);
}

export function writeContainerFile(id: number, payload: ContainerFileWriteRequest) {
  return apiPost<ContainerFileWriteResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/write`, payload);
}

export function uploadContainerFiles(
  id: number,
  path: ContainerFileUploadRequest["path"],
  files: File[],
  overwrite: ContainerFileUploadRequest["overwrite"] = true,
) {
  const form = new FormData();
  form.set("path", path);
  form.set("overwrite", String(overwrite));
  files.forEach((file) => form.append("files", file));
  return apiForm<ContainerFileUploadResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/upload`, form);
}

export function downloadContainerFiles(id: number, params: DownloadContainerFilesParams) {
  const query = new URLSearchParams();
  params.path.forEach((path) => query.append("path", path));
  return apiBlob(`${SANDBOX_CONTAINERS_PATH}/${id}/files/download?${query.toString()}`);
}

export function copyContainerFiles(id: number, payload: ContainerFileCopyRequest) {
  return apiPost<ContainerFileCopyResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/copy`, payload);
}

export function moveContainerFiles(id: number, payload: ContainerFileMoveRequest) {
  return apiPost<ContainerFileMoveResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/move`, payload);
}

export function deleteContainerFiles(id: number, payload: ContainerFileDeleteRequest) {
  return apiPost<ContainerFileDeleteResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/delete`, payload);
}

export function createContainerDirectory(id: number, payload: ContainerFileMkdirRequest) {
  return apiPost<ContainerFileMkdirResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/mkdir`, payload);
}

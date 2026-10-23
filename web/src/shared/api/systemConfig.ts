import { apiGet, apiPatch, apiPost } from "./client";
import type {
  CheckSearchProvidersRequest,
  CheckSearchProvidersResponse,
  FetchUpstreamModelsRequest,
  FetchUpstreamModelsResponse,
  GetInstanceConfigResponse,
  UpdateInstanceConfigRequest,
  UpdateInstanceConfigResponse,
} from "./types";

const SYSTEM_CONFIG_PATH = "/api/system-config";

export function getInstanceConfig() {
  return apiGet<GetInstanceConfigResponse>(`${SYSTEM_CONFIG_PATH}/instance`);
}

export function updateInstanceConfig(payload: UpdateInstanceConfigRequest) {
  return apiPatch<UpdateInstanceConfigResponse>(`${SYSTEM_CONFIG_PATH}/instance`, payload);
}

export function fetchUpstreamModels(payload: FetchUpstreamModelsRequest) {
  return apiPost<FetchUpstreamModelsResponse>(`${SYSTEM_CONFIG_PATH}/upstream-models`, payload);
}

export function checkSearchProviders(payload: CheckSearchProvidersRequest) {
  return apiPost<CheckSearchProvidersResponse>(`${SYSTEM_CONFIG_PATH}/search-providers/check`, payload);
}

from fastapi import APIRouter, Depends

from handler.system_config.config import (
    check_search_providers_handler,
    fetch_upstream_models_handler,
    get_instance_config_handler,
    update_instance_config_handler,
)
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES
from schema.common.responses import CommonResponse
from schema.system_config.config import (
    CheckSearchProvidersResponse,
    FetchUpstreamModelsResponse,
    InstanceConfigSchema,
    UpdateInstanceConfigResponse,
)


ADMIN_ONLY = [Depends(require_admin)]

router = APIRouter(prefix="/system-config", tags=["system-config"])

router.add_api_route(
    "/instance",
    get_instance_config_handler,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[InstanceConfigSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/instance",
    update_instance_config_handler,
    methods=["PATCH"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[UpdateInstanceConfigResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

router.add_api_route(
    "/upstream-models",
    fetch_upstream_models_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[FetchUpstreamModelsResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

router.add_api_route(
    "/search-providers/check",
    check_search_providers_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[CheckSearchProvidersResponse],
    responses=COMMON_ERROR_RESPONSES,
)

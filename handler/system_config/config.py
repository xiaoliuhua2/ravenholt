from schema.common.responses import CommonResponse
from schema.system_config.config import (
    FetchUpstreamModelsRequest,
    FetchUpstreamModelsResponse,
    UpdateInstanceConfigRequest,
    UpdateInstanceConfigResponse,
)
from service.system_config.config import (
    fetch_upstream_models,
    get_instance_config,
    update_instance_config,
)


async def get_instance_config_handler() -> CommonResponse:
    result = await get_instance_config()
    return CommonResponse(data=result.config)


async def update_instance_config_handler(request: UpdateInstanceConfigRequest) -> CommonResponse:
    result = await update_instance_config(request)
    return CommonResponse(data=UpdateInstanceConfigResponse(config=result.config, restarted=result.restarted))


async def fetch_upstream_models_handler(request: FetchUpstreamModelsRequest) -> CommonResponse:
    models = await fetch_upstream_models(request.base_url, request.api_key)
    return CommonResponse(data=FetchUpstreamModelsResponse(models=models))

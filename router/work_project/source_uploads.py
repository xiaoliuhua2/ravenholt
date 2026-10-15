from fastapi import APIRouter, Depends, File, UploadFile

from handler.work_project.source_uploads import upload_work_project_source_handler
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES
from schema.common.responses import CommonResponse
from schema.work_project.source_uploads import WorkProjectSourceUploadSchema


router = APIRouter(
    prefix="/work-projects",
    tags=["work-projects"],
    dependencies=[Depends(require_admin)],
)


async def upload_work_project_source_route(
    files: list[UploadFile] = File(),
) -> CommonResponse[WorkProjectSourceUploadSchema]:
    return await upload_work_project_source_handler(files=files)


router.add_api_route(
    "/source-uploads",
    upload_work_project_source_route,
    methods=["POST"],
    response_model=CommonResponse[WorkProjectSourceUploadSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

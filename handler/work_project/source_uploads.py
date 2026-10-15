from http import HTTPStatus

from fastapi import UploadFile

from schema.common.responses import CommonResponse
from service.work_project.source_uploads import store_source_upload


async def upload_work_project_source_handler(files: list[UploadFile]) -> CommonResponse:
    """接收源码归档（multipart）并解压到工作区。

    返回的 ``server_path`` 由前端直接作为 binary 资产的 path 使用（源码审计的输入）。
    """
    if not files:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message="no source archive uploaded")
    if len(files) > 1:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message="upload one source archive at a time")

    upload = files[0]
    try:
        schema, error = await store_source_upload(upload.filename or "", upload.file)
    finally:
        await upload.close()
    if schema is None:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=error or "invalid source archive")
    return CommonResponse(message="source archive uploaded", data=schema)

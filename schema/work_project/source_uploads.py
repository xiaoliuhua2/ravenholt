from pydantic import BaseModel, ConfigDict, Field


class WorkProjectSourceUploadSchema(BaseModel):
    """一次源码包上传的结果；``server_path`` 可直接作为 binary 资产的 path 使用。"""

    model_config = ConfigDict(from_attributes=True)

    token: str = Field(description="本次上传的存储令牌（工作区内的目录名）。")
    slug: str = Field(description="解压后的顶层目录名，也是沙箱内的挂载目录名。")
    server_path: str = Field(description="解压后的服务器绝对路径（binary 资产的 path）。")
    file_count: int = Field(default=0, ge=0, description="解压出的文件数。")
    total_bytes: int = Field(default=0, ge=0, description="解压出的总字节数。")
    skipped_entries: int = Field(default=0, ge=0, description="被跳过的条目数（依赖目录、符号链接等）。")

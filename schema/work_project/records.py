from pydantic import BaseModel

from schema.work_project.assets import WorkProjectAssetSchema
from schema.work_project.findings import WorkProjectFindingSchema
from schema.work_project.graph import WorkProjectGraphSnapshotSchema
from schema.work_project.projects import WorkProjectSchema


class WorkProjectRecordsSchema(BaseModel):
    assets: list[WorkProjectAssetSchema]
    # 资产可能被快照上限截断；总数单独给，前端计数与「显示更多」都以它为准。
    assets_total: int = 0
    findings: list[WorkProjectFindingSchema]
    graph: WorkProjectGraphSnapshotSchema


class WorkProjectRecordSnapshotSchema(BaseModel):
    project: WorkProjectSchema
    records: WorkProjectRecordsSchema

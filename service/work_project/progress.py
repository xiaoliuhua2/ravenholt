from schema.work_project.projects import WorkProjectStatus, WorkProjectTaskSchema, WorkProjectTaskStatus


def calculate_work_project_progress(tasks: list[dict] | list[WorkProjectTaskSchema]) -> float:
    if not tasks:
        return 0
    progress_values = [
        WorkProjectTaskSchema.model_validate(task).progress
        for task in tasks
    ]
    return round(sum(progress_values) / len(progress_values), 2)


def derive_work_project_status(
    tasks: list[dict] | list[WorkProjectTaskSchema],
    current_status: WorkProjectStatus,
) -> WorkProjectStatus:
    if current_status == WorkProjectStatus.CANCELED:
        return WorkProjectStatus.CANCELED
    if not tasks:
        return WorkProjectStatus.WORKING

    statuses = [
        WorkProjectTaskSchema.model_validate(task).status
        for task in tasks
    ]
    if all(status == WorkProjectTaskStatus.DONE for status in statuses):
        return WorkProjectStatus.COMPLETED
    return WorkProjectStatus.WORKING


def derive_work_project_lifecycle_status(
    *,
    current_status: WorkProjectStatus,
    has_sessions: bool,
    any_session_running: bool,
    all_sessions_finished_cleanly: bool,
) -> WorkProjectStatus:
    """以会话生命周期判定项目"跑没跑完"。

    任务勾选比例不能当收尾判据：子代理/主控收尾时并不总会把 TODO 逐条勾掉，
    残留待办会把已经跑完的项目永远卡在"进行中"。真实的收尾信号是会话运行终态：
    没有任何会话在跑，且每个会话都曾结束、结束时无 run_error。
    """
    if current_status == WorkProjectStatus.CANCELED:
        return WorkProjectStatus.CANCELED
    if not has_sessions or any_session_running:
        return WorkProjectStatus.WORKING
    if all_sessions_finished_cleanly:
        return WorkProjectStatus.COMPLETED
    return WorkProjectStatus.WORKING

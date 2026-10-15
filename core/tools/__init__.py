"""Agent tool implementations.

.. deprecated::
    原生 registry 轨道的工具（``local_shell`` / ``blackboard`` / ``work_project*`` /
    ``src_hunt``）已随该轨道的驱动链一起删除。

    strix 原生轨道改用 SDK 能力 + ``core.strix_runtime`` 里的工具：
    ``sandbox_session``（SDK ``Shell``/``Filesystem``）、``skill_routes``（``route_skills``）、
    ``evidence_tools``（``record_evidence``）、以及 strix 自带的 ``tools/`` 全套。

    原 ``knowledge`` 工具模块（以及 ``.ravenholt/agents/{code}/`` 下的角色提示词与人设）随该
    轨道一并删除：它们只在原生 registry 轨道里被使用，单轨化后已无任何读取点。本包目前只剩
    ``sandbox``（``SANDBOX_SKILLS_DIR`` 常量）。
"""

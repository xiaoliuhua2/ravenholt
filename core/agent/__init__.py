"""Agent declarations and registry package.

.. deprecated::
    原生 registry 轨道的静态专家 agent 体系（``specs`` / ``instructions`` /
    ``SessionAgentGraph``）已随 strix 单轨化整体删除。

    现在的执行引擎只有一个：``core.strix_runtime`` 的 ``build_agent`` 构建 strix 原生
    ``SandboxAgent`` —— 一个 root 智能体，自己用 ``create_agent`` 派生 / 回收子代理，
    自己用 SDK 的 ``Shell`` / ``Filesystem`` 能力操作沙箱。

    本包只保留仍被平台依赖的模块：

    - ``registry``（``AgentRegistry``）：已配置 agent code 的只读视图，供 agent 列表
      接口与会话 meta 校验使用；
    - ``models``（``build_openai_model``）：仍被 ``core.strix_runtime`` 与
      ``core.conversation.compaction`` 使用；
    - ``model_input``：``models`` 的输入适配层；
    - ``constants``（``DEFAULT_AGENT_CODE``）：仍被 handler / service 使用。
"""

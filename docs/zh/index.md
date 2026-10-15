---
# https://vitepress.dev/reference/default-theme-home-page
layout: home
pageClass: ravenholt-docs-home

hero:
  name: Ravenholt
  text: 红队协作工作台
  tagline: 面向授权渗透测试与漏洞挖掘的多智能体协作平台
  image:
    src: /ravenholt-logo-light.svg
    alt: Ravenholt Logo
  actions:
    - theme: brand
      text: 快速开始
      link: /zh/guide/quick-start
    - theme: alt
      text: 说明文档
      link: /zh/guide/overview

features:
  - title: 多智能体协同
    details: 主管智能体按任务动态派生专家智能体，把情报侦察、漏洞验证、代码分析与攻击路径梳理并行推进，提升授权测试的执行效率与覆盖范围。
  - title: 项目化架构
    details: 以 WorkProject 统一管理测试范围、任务、会话、资产、漏洞发现和攻击路径，让红队工作过程可组织、可追踪、可复盘。
  - title: 异步任务运行时
    details: 长命令和子智能体可后台执行，完成后自动唤醒上下文，减少等待并避免任务状态丢失。
  - title: 受控沙箱执行面
    details: 基于 Docker 的定制沙箱容器提供命令执行、文件管理、网页终端与 noVNC 远程画面；容器按会话自动 provision，出口可绑定代理。
  - title: 策略治理与审计
    details: 红线策略对高风险动作做 fail-closed 判定，需人工确认的动作进入审批队列；关键动作与拦截原因写入审计日志。
  - title: 结构化证据沉淀
    details: 持续记录资产、漏洞发现、关系图和攻击路径，发现必须携带可复现证据方可确认，使验证质量、复盘效率和交付材料更稳定。
---

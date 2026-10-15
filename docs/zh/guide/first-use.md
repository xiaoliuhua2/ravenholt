---
title: 首次使用
editLink: true
---

# 首次使用

本文档将首先介绍 Ravenholt 的整体功能，然后通过一次从 0 到 1 自动化完成 CTF 解题任务的逐步讲解，介绍系统的各个模块和使用方式。

## 系统概览

根据配置的监听地址和端口，访问跳转至落地页：

![landing](/images/landing.png)

点击「进入操作台」按钮跳转至登录页，输入配置的管理员账号与密码，登录成功后即进入管理后台。

系统包含以下核心模块：

1. 操作台（Playground）：核心工作区，与智能体协作的区域，含沙箱容器终端与文件管理。
2. 工作项目（Work Projects）：工作项目的创建、编辑与审查。
3. 出口代理（Egress Proxies）：配置 HTTP/HTTPS/SOCKS5 代理，作为沙盒容器的网络出口。
4. 策略审批（Policy Approvals）：红线策略下高风险动作的审批队列。
5. 审计日志（Audit Log）：关键动作与事件的审计追踪。
6. 系统用户（System Users）：用户信息与角色管理。
7. 系统配置（System Config）：运行参数配置，支持热更新。

### 界面一览

**操作台（Playground）** —— 与智能体协作的主工作区：

![playground](/images/playground.png)

**工作项目（Work Projects）** —— 项目管理、记录与图谱：

![work-projects](/images/work-projects.png)

**策略审批（Policy Approvals）** —— 红线策略下高风险动作的审批队列：

![policy-confirmations](/images/policy-confirmations.png)

**审计日志（Audit Log）** —— 关键动作与事件的审计追踪：

![audit-events](/images/audit-events.png)

**出口代理（Egress Proxies）** —— 沙箱容器的受控网络出口：

![egress-proxies](/images/egress-proxies.png)

**系统用户（System Users）** —— 账号与角色：

![system-users](/images/system-users.png)

**系统配置（System Config）** —— 运行参数与集成配置：

![system-config](/images/system-config.png)

## 开始工作

以下内容从系统初始状态开始，逐步完成一道 CTF 赛题。沙盒容器无需手工创建：与智能体开始协作时，平台会按会话自动 provision。

### 创建项目

以一道 CTF 赛题为目标，在「工作项目」中新建一个工作项目，填写项目名称、项目类型、项目描述、负责人员等基础信息，并设置已知的资产信息。

### 任务实施

工作项目创建完成后，操作台的会话列表中就会出现对应的选项，点击进入创建一个新会话，即可正式与智能体协作。通过自然语言要求攻破 CTF 题目获取 flag，最终交付 write-up。

任务执行过程中，可以在项目的记录窗口中查看实时进度：资产、发现、关系与图谱共同把过程沉淀为长期的证据留存。

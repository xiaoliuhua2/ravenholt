---
# https://vitepress.dev/reference/default-theme-home-page
layout: home
pageClass: ravenholt-docs-home

hero:
  name: Ravenholt
  text: Red Team Collaboration Workbench
  tagline: A multi-agent collaboration platform for authorized penetration testing and vulnerability discovery
  image:
    src: /ravenholt-logo-light.svg
    alt: Ravenholt Logo
  actions:
    - theme: brand
      text: Quick Start
      link: /en/guide/quick-start
    - theme: alt
      text: Documentation
      link: /en/guide/overview

features:
  - title: Multi-agent collaboration
    details: The lead agent dynamically spawns expert agents per task, driving intelligence gathering, vulnerability validation, code analysis, and attack-path mapping forward in parallel to improve the execution efficiency and coverage of authorized testing.
  - title: Project-oriented architecture
    details: Use WorkProject to centrally manage test scope, tasks, sessions, assets, vulnerability findings, and attack paths, making the red team workflow organized, traceable, and reviewable.
  - title: Asynchronous task runtime
    details: Long commands and sub-agents can run in the background and automatically wake their context when they finish, reducing waiting and avoiding task state loss.
  - title: Controlled sandbox execution surface
    details: Docker-based custom sandbox containers provide command execution, file management, a web terminal, and noVNC remote view; containers are provisioned automatically per session, and their egress can be bound to a proxy.
  - title: Policy governance and auditing
    details: The red-line policy makes fail-closed decisions on high-risk actions, actions requiring human confirmation enter the approval queue, and key actions and block reasons are written to the audit log.
  - title: Structured evidence retention
    details: Continuously record assets, vulnerability findings, relationship graphs, and attack paths. A finding must carry reproducible evidence before it can be confirmed, making validation quality, review efficiency, and deliverables more consistent.
---

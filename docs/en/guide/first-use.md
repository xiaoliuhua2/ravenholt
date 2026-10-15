---
title: First Use
editLink: true
---

# First Use

This guide first introduces the overall capabilities of Ravenholt, then walks through a complete CTF task from initial setup to automated solving. The walkthrough explains the main system modules and their intended usage.

## System Overview

Access the configured listening address and port to enter the landing page:

![landing](/images/landing.png)

Click the "Enter Playground" button to open the login page, then enter the configured administrator account and password. After successful authentication, you enter the management console.

The system contains the following core modules:

1. Playground: the primary workspace for collaborating with the agents, including the sandbox container terminal and file manager.
2. Work Projects: creation, editing, and review of work projects.
3. Egress Proxies: configures HTTP/HTTPS/SOCKS5 proxies used as the egress for sandbox containers.
4. Policy Approvals: the approval queue for high-risk actions under the red-line policy.
5. Audit Log: an auditable trail of key actions and events.
6. System Users: user and role management.
7. System Config: runtime configuration with hot updates.

### UI Gallery

**Playground** — the primary workspace for collaborating with the agents:

![playground](/images/playground.png)

**Work Projects** — project management, records, and graphs:

![work-projects](/images/work-projects.png)

**Policy Approvals** — the approval queue for high-risk actions under the red-line policy:

![policy-confirmations](/images/policy-confirmations.png)

**Audit Log** — an auditable trail of key actions and events:

![audit-events](/images/audit-events.png)

**Egress Proxies** — the controlled network egress for sandbox containers:

![egress-proxies](/images/egress-proxies.png)

**System Users** — accounts and roles:

![system-users](/images/system-users.png)

**System Config** — runtime parameters and integration configuration:

![system-config](/images/system-config.png)

## Start Working

The following sections start from a clean system state and complete a CTF challenge. Sandbox containers do not need to be created manually — the platform provisions them per session when you start collaborating with the agents.

### Create a Project

Using a CTF challenge as the target, create a work project in **Work Projects**. Fill in the project name, project type, description, responsible users, and other basic information, and enter the known asset information.

### Execute the Task

Once the work project is created, it appears in the Playground session list. Open it, create a new session, and start collaborating with the agents. Use natural language to instruct the agents to solve the CTF challenge, obtain the flag, and finally deliver the write-up.

During execution, open the project's records window to inspect real-time progress: assets, findings, relationships, and graphs together preserve the process as long-term evidence.

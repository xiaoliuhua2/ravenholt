---
name: "10-cors-vuln-report-priority"
description: "CORS（永久 · 不挖）"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# CORS（永久 · 不挖）

> **用户 2026-08-12 定死：** 以后 **CORS 不挖**。落不落报告见 `03-vuln-report-format.md`。

## 硬规定

1. **不挖：** 类型矩阵、进站节奏里 **不再** 把 CORS 当必测/必推进项  
2. 精力转 **注入 / SSRF / XSS / RCE / 越权 / 未授权业务敏感读 / 提权 / 逻辑** 等

## 一句话

**CORS = 不挖。**

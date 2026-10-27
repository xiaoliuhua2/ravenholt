---
name: "crlf-injection-test"
description: "crlf-injection-test（几乎不交）"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# crlf-injection-test（几乎不交）

> 纯 CRLF 头注入默认不写。Host 毒重置走 `http-host-header-test.md`。Ghost Bits 邮件/走私用公式 `chr((k<<8)|T)`，见 `ghost-bits-cast-test.md`。

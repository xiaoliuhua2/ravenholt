---
name: "api-gateway-oracle"
description: "API 网关路由预言机 + Spring 参数递归枚举"
---

# API 网关路由预言机 + Spring 参数递归枚举

适用：目标只给了一个 APISIX/openresty/Spring Cloud Gateway 网关壳，打任何路径都是 404，
看起来"没东西"，实际后端挂着一堆微服务但缺路由字典。

## 一、APISIX 路由预言机（先找活的服务前缀）

同一网关对不同路径会返回**结构不同**的错误体，靠这个区分服务前缀是否注册：

| 响应 | 含义 |
|------|------|
| `{"error_msg":"404 Route Not Found"}` | 该前缀**未注册** |
| `{"code":403,"message":"Bad Request"}` | 前缀**存在**，被鉴权插件拦（capis-ecs / capis / web-simu 型） |
| `{"code":401,"message":"Unauthorized!"}` | 前缀**存在**，需 appkey（openapi 型） |
| `Not Found`（纯文本，openresty） | 未注册 |
| `{"timestamp":...,"status":404,"error":"Not Found","path":"/xxx"}` | **后端是 Spring 应用**，且网关剥离前缀后转发（path 字段回显剥离后的路径） |

做法：写一个前缀字典（user/order/pay/account/coupon/auth/admin/api/v1/open...）打 `<前缀>/test`，
只扫前缀级，别扫方法级——网关按前缀匹配，方法名对不对都返回同一个 403，扫不出东西。

实测（嘀嗒 2026-09-08）：capis-ecs+capis+web-simu 活前缀 = user/pay/coupon/account；
openapi 活前缀 = user/account/auth。一次扫描 13 个前缀、每个 0.6s 即可。

## 二、Spring 参数递归枚举（拿完整参数签名）

Spring 的 `MissingServletRequestParameterException` 会**回显下一个必填参数名**，
循环补参就能把端点参数签名一个个逼出来，不需要源码、不需要抓包：

```
GET /x            -> Required String parameter 'user_cid' is not present
GET /x?user_cid=1 -> Required String parameter 'session_token' is not present
GET /x?user_cid=1&session_token=1 -> Required ... 'session_act_id' is not present
GET /x?user_cid=1&session_token=1&session_act_id=1 -> 真实业务码
```

脚本套路：`while` 里正则抓 `parameter '([a-zA-Z_]+)' is not present`，缺谁补谁（值填 `1`），
直到不再出现该异常。同时会把 `exception` 类名、`path` 一起吐出来（顺带的信息泄露证据）。

**判洞关键**：补完参数后的终态响应决定有没有洞——
- 返回业务错误码（如 107「请升级到最新版本」、401、2005）= 需要真实凭据，**证伪**；
- 返回数据/token = 未授权，成洞。

别急着报"参数名泄露"当漏洞，多数 SRC 不收；它的价值是**给你完整参数签名**去打下一步。

## 三、actuator / swagger 在网关后的判定

- `/actuator/env`、`/actuator/heapdump` 被 WAF 拦（624）≠ 有专用规则，**先排除频控**再下结论；
- 网关 403（openresty 层）= 路径存在但被网关黑名单拦，换前缀拼（如 `/auth/actuator/health`）；
- Spring Security 401 "Full authentication is required" = 端点真实存在（swagger-ui.html 常见），
  值得再试 swagger-resources / v2/api-docs / webjars 静态资源这些常被 permitAll 的旁路。

## 四、节奏

这两个动作都在同一网关上连打，极易触发 IP 频控。间隔 ≥0.6s，总量控制在 20~30 个请求一轮，
被 624 就换另一个资产（不同 IP）继续，别硬顶。

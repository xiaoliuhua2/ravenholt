---
name: "file-upload-test"
description: "文件上传漏洞测试手册"
---

> 写不写只认 `../03-vuln-report-format.md`。本篇是测法：别停在能传能下，跟可执行/路径/SSRF/跨用户业务对象。
> 短表指针用标题搜。PHP 马 / GIFAR / ImageTragick / 英文附件已砍；没对象存储不要空打跨桶。
> **2026-09-21 留痕**：下文「传统上传点…」一节来源任务定级为**中危**，按用户当日明确指令补入（原文门槛为「来源须高危/严重、中危不进」）——此为显式破例，非门槛松动；具体目标已脱敏。

# 文件上传漏洞测试手册

## 测试流程（开场）

找上传点（头像/附件/导入/富文本）→ 先传正常文件看路径、是否重命名、落 CDN/OSS 还是本机、能不能直接打开。别停在能传能下：跟覆盖他人对象、带签读、可执行/路径/SSRF。后缀/Content-Type/解析绕过现场按栈自己变。

### 传统上传点：后缀校验的判法与「结构性无解」识别（2026-09-21 补）

> 来源：某电信类 BSS 系统实测 30+ 组（定级见文首留痕）。本节是开场第 8 行
> 「后缀/Content-Type/解析绕过现场按栈自己变」的细化落地。

**认**：附件/导入/报表类上传点；同一产品里**成对出现多个上传 servlet**（`XxxUploadServlet.do` / `XxxImportServlet.do` / `XxxAddServlet.do` 各一套校验）；
服务端把上传文件**重命名**（`日期时间+随机+扩展名` 一类）后再落盘。

**第一步不是打手法，是先答两个问题**（决定后面整张手法清单有没有意义）：

1. **校验段 == 落地区段？**
   反推是否 `ext = filename.substring(filename.lastIndexOf("."))`，且**重命名时用的也是同一个 `ext`**。
   判法：连传 `a.txt` 与 `a.jpg`，各记落地名，看落地扩展名是不是**照抄原文件名的最后一段**。
   是 ⇒ **所有「让校验看 A、落地得 B」的思路结构上失效**（双扩展名 / 尾点 / 尾空格 / ADS / 参数错位 / 解析器歧义全废）——
   因为能不能落地 `.jsp` 只取决于 `ext`，而 `ext==".jsp"` 必被白名单拒，**矛盾**。
   ★ 到这里就可以直接判「该校验绕过不了」，**不必把手法清单打完**（省下的时间是本节的主要价值）。
2. **白名单 / 黑名单 / 空后缀短路？**（三枪定界）
   - 传一个绝对不在任何名单里的后缀（`.abc`）：**过 ⇒ 黑名单**；**拒 ⇒ 白名单**
   - 传**无点文件名**（`shell`）：报异常/内部错误 ⇒ `lastIndexOf` 返回 **-1**，实现没做边界处理
   - 传 **`x.jsp.`（尾点）**：**若过 ⇒ 命中"空后缀短路"经典缺陷**（`if(ext!=null && !ext.equals(""))` 才查名单），
     叠加 Windows 写盘自动去尾点 ⇒ 落地成 `x.jsp` ⇒ **直接 getshell**。★ 这一枪优先于其他所有手法

**打（按"骗过哪一段"分类，不按名字罗列）**：

- **A 类｜骗校验、指望保留原名落地**（只在"落地不重命名"的系统上成立）：
  `shell.jsp.jpg` `shell.jpg.jsp` `shell.jsp..jpg` `shell.png.jpg.jsp` `shell.jsp;.jpg` `shell.jsp:.jpg` `shell.jsp .jpg` `shell.jsp#.jpg` `shell.jsp%0d%0a.jpg`
  ★ 环境差异要分清：Apache+PHP 是"**从后往前找可识别扩展名**"（故 `x.jsp.jpg` 被当 PHP 跑）；
  **Tomcat 的 `*.jsp` 是精确后缀匹配** ⇒ 同一手法在 Java 栈本就不成立
- **B 类｜打 ext 取值边界**：尾点 / 尾空格 / `\x00` / `::$DATA` / `::$data.` / 尾 `\` / 尾 `/` / 多重点 `......` /
  **`x.j\sp`（反斜杠插在扩展名中间 —— 制造"校验段与落地区段不同"的机会）** / RTLO `\u202E` / 超长名截断
- **C 类｜参数与解析器错位**：`file_path=.png` + `filename=.jsp`（有的实现查前者、存后者）/ 只给 `filename*`(RFC5987) /
  同 part 重复 `filename=` / 两个 `file` part / `Content-Type: image/png` 伪造 / `SERVICE_TYPE_NAME` 一类"业务类型"参换值（可能按类型选白名单）
- **D 类｜独立入口（最容易漏，每站必做）**：
  ① ★ **抓包全量搜 `multipart/form-data`** —— 本任务就藏着**第三个上传 servlet**，它**零扩展名校验**，
     而另两个一个有白名单、一个零校验；**只看已知的那一两个上传点就会把整站判错**
  ② **Tomcat PUT**（CVE-2017-12615）：`PUT /x.jsp/`、`PUT /x.jsp%20`、`PUT /x.jsp::$DATA`；**201/204 = 写入成功**，
     405 = nginx 层拦（该 CVE 不适用，可收）
  ③ 配置文件落地（`.htaccess` / `web.config` / `uwsgi.ini` / `package.json`）—— 仅对应栈适用

**算成**：三条件**缺一不算** —— ① 传上去（绕过校验）；② **取得回来**（路径可枚举，或有真能读的下载口）；③ **被解析**（目录在 web 根下 + 映射到脚本引擎）。
★ 本任务三条全断在②：同一 webapp 下**三个 `xxxServlet.download` 端点全是假接口** ——
`fileName` 传空 / 不存在 / **真实值**，一律**逐字节回 22B `{"success":"success"}`、耗时恒定 3.0s** ⇒ 附件不可达，RCE 链接不上。

**假点（只记形态不是洞，别在同一形态上反复打）**：
- **「校验通过」≠「能执行」**：`x.jsp.jpg` 过了校验，但落地名是 `x.jpg`（重命名把中间段丢了）。
  写"任意文件上传"之前，**先把落地名读到**
- **假下载接口**：`fileName` 空 / 不存在 / 真实值，响应**逐字节相同** ⇒ 服务端根本没读文件，**不是"文件不存在"**
- 「不跳登录」≠「有鉴权缺口」（过滤器白名单 ≠ 业务准入）
- 「大小写绕过」的前提是**比对不做大小写归一** —— 连 `.GIF` 都被拒 ⇒ 该校验大小写敏感，这条整段可收

**同源副产物（判 XSS 时用）**：
- **一枪测出过滤器字符集**：提交由 `'"&()<>` 拼成的标记，从回读**逐字符比对**
  （本任务：只把 `< > & ( )` 转全角同形字，**`'` 与 `"` 原样放行**）
- **列元数据接口可枚举注入位**：若列表由「`service_name=<列定义service>&service_code=<列表名>`」这类接口驱动，
  可批量取列定义，找 `COL_TYPE=7` / `COM_TYPE=21,22`（渲染成 `value="' + cellValue + '"`，**只需 `"` 闭合、无需尖括号**）
- ★ **不可利用时的结论写法定式**：写「**当前列配置 + 当前过滤器下不可利用，成因是①…②…**」，**不是"这个系统安全"** ——
  因为任一条变化（新增一个 `COL_TYPE=7` 的列表 / 换用把值拼进属性又只挡尖括号的组件）就是可用的存储型 XSS。
  这类"**成因是巧合**"的结论，交付价值高于"没打穿"

**★ 耗时是一把尺子（通用）**：先测静态资源与普通 servlet 的**耗时基线**，再看上传/下载口 ——
本任务静态 0.01s、普通 servlet 0.03s，而**上传与下载的"成功分支"恒定 3.0-3.1s、"拒绝分支"0.03s**
⇒ 光看耗时就能分辨走了哪个分支，且证明 `success` 真落了盘（慢 IO），**不必重发**。

**★ 配套的通用真错（比绕过更常见）**：「系统错误」≠「接口不存在」。
本任务业务查询一律回 `{"success":"fail","errormsg":"系统错误"}`，一度被判成"服务端无此 service / 版本不匹配"，
真因只是**请求体编码**：`data=dict`（被工具序列化成 **JSON body**）→ 系统错误；`data=urlencode(dict)`（**真 form body**）→ `{"total":18,…}` 正常。
**动作**：同一接口换一种 body 编码（JSON ↔ form ↔ 空体）再打一次，零成本自证。

### STS / 对象 key 通配覆盖（短表有指针）

认：对象存储（BOS/OSS/S3/TOS 一类）上传先申请 STS/预签名；对象 key 常是文件 md5；桶名按日期或批次递增。或 assumerole 一类领钥匙口，请求里的 `filename` / `Action` 会被拿去拼 Policy。下面 xluser / AES / `1.jpg` 是常见皮，**没有这字仍打通配**。

打：

1. 申请凭证的 `identifier` / `key` / `object` / `prefix` / `filename` **长度不校验**时，试 `*`、`**`，再试**置空**和 `/`（有的实现空前缀 = 整桶）  
2. 一个 `*` 可能落到空桶；**两个以上**可能命中当前业务桶，凭证 `key` 变成通配当前桶  
3. path / `actionName` / 拼进 Policy 的路径参试 `../../../`、`../../../&/../../`，看签出来的范围是不是扩到根  
4. 别人文件的对象 key 往往是 md5：打开文档页，在 JS/接口里搜 `md5sum` / `md5`，不用下载、不用付费  
5. 用刚领到的 STS，把上传 path 设成对方那个 md5，覆盖对象  
6. assumerole 另打一枪：`filename=*-*`（或 `*`）、`Action=*`。有的实现是**后段 Policy 盖前段**，钥匙变成整桶。通了先 `list_objects`，再删/盖列出来的 key。**List/Delete 403 别停**：对任意 key GET/PUT。领钥 XHR 不带登录头也打。**sibling drive 匿名票 `illegal user id` 不等于本网关也拒**：匿名 xluser 票过闸的 STS 口照打。query `upload_dir`/`dir` 原样进 OSS Policy 时填 `*`。页面走 CDN 时，强制刷新或等缓存过完再验收  
7. PUT 时头里试 `x-cos-acl: public-read`、`x-cos-grant-full-control: id="你的UIN"`（OSS/S3 对等头一样）。**对象真变成公有读、或控制权到你的 UIN** 才算；只 200 不算接管
8. 没有「文件已存在」预言时仍猜短原文件名（`1.jpg`/`2.png`/`5.jpg`）匿名 GET CDN。token 口若前端写死 AES/盐，未登录自己算 sign，`filename=*` 常直接下发 appId+bucket，CDN 前缀拼出来就能下**他人证件照**  
9. **落地页写死 supabase / nocode `role=anon` JWT 时，rest 表 CRUD 不是终点。** 带 `apikey` + `Authorization: Bearer` 打 `POST /storage/v1/object/{桶}/{官方前缀/探测key}`。官方封面/案例图常在 `use-cases/`、`covers/` 一类前缀。第一次 POST 自己的探测文件；同一对象名再 POST，头加 `x-upsert: true`，正文改成另一串标记。公开 `GET /storage/v1/object/public/{桶}/{key}` 对照两次正文。**不要真盖官方运营图**，同前缀能盖自己刚传的 = 官方同前缀同样能盖。打完 DELETE 探测文件。rest `/rest/v1/` 403 别停，存储 REST 常另开。

算成：再打开/下载**对方那篇/那张图**，内容变成你传的；或 list 出别人的 key 并能删/盖；或官方前缀上 `x-upsert` 把探测文件盖成第二串标记（同前缀官方对象同一把钥）。只证明自己能传到自己的 key → 假点。

假点：`*` 只签发废桶；通配了但覆盖 403；改的是自己的对象；策略服务端写死盖不掉；只通自己前缀；CDN 一直不刷新看起来没盖上。单站没中不删短表这行。

和 S3 预签名「改自己的 Content-Type」、和「带签 URL 改租户读他文件」、和下面「桶策略对匿名全开」「签名没绑 Host」「签名覆盖 Content-Type」都不是一条：本条是 **凭证范围被通配成整桶，覆盖或清掉他人对象**。

### 签名没绑 Host（短表有指针）

认：COS / OSS / S3 带签 URL；query 里 `q-header-list`、`SignedHeaders`、`X-Amz-SignedHeaders` **没有 host**。有对象存储带签才打，没有不要空换域名。

打：

1. 看签名参数里签了哪些头。没有 `host` 再往下。  
2. 把 URL 的主机换成**同账号另一个桶**的域名（证书 SAN、报错、控制台、JS 里抄），path 和签名 query 先不动。  
3. 再加 `?uploads`（或已有 query 后 `&uploads`）打 ListMultipartUploads；能 GET 对象也打。

算成：列出或读到**别的桶**里的对象。只换域还是自己这个桶 → 没成。

假点：签名罩住 Host；换域 403；只有自己这个桶。单站没中不删短表这行。

和 STS `*`（钥匙范围被通配）、和带签 URL 只改租户字段 **不是一条**：本条是 **Host 没进签名，同一把签能打到别的桶**。

### 签名覆盖 Content-Type（短表有指针）

认：对象内容你能控（自己传的或 STS 能盖的）；对象上的 Content-Type 被卡死（image/jpeg 一类）；手里有临时钥或能再出预签名。

打：

1. 上传时改 CT 那一枪还打（`text/HtMl`、`text/html,image/png`）。那是「签的时候没把 CT 签进去」。  
2. **事后再签**：用临时钥给**已有对象**出一枪带 `response-content-type=text/html`（COS/OSS 支持签名覆盖响应头）的 GET。  
3. 用这把新签 URL 在浏览器打开，不要只看 curl 的 Content-Type。

算成：浏览器当 HTML 执行（存储 XSS）。下载仍是附件/原 CT → 没成。

假点：签名接口拒这个参；只能改自己不可达的对象；`X-Content-Type-Options: nosniff` 且 CT 仍是图。单站没中不删短表这行。没对象存储、没临时钥不要空签。

和「上传 PUT 时改 Content-Type」不是一条：那条改的是**写入时**的类型；本条是 **读的时候用签名把响应头盖成 HTML**。

### webpack 明文对象存储永久钥（短表有指针）

认：管理台 / 运营后台 webpack 把生产 `accessKeyId`+`secretAccessKey`（MSS / S3 一类永久钥）打进 JS。或 Weblogic `/console/login/LoginForm.jsp` 内联 `_reportCfg` 一类的 `SRV_` 钥。上传签 `getUploadSign` 是前端 HMAC-SHA1 算 policy，不是走登录后的 STS 口。policy 里 `starts-with $key` 经常是空串。

打（不登录）：

1. 抄 online/prod 的 AK/SK（实值只进报告）  
2. 自己算 POST policy，expiration 拉长，`starts-with $key` 按 JS 原样（空就空）  
3. POST 桶：对照假签 `SignatureDoesNotMatch`、无签 `conditions has no signature`  
4. 任意 key PUT 后 CDN GET；DELETE 自己刚传的证明钥能写。官方页面已经引用的对象试覆盖  
5. List/PUT 403 别停：先 `GetBucketLocation`。对照假 AK `InvalidAccessKeyId`。页面桶名拼错（staic/static）试邻近  

算成：完整永久云钥能签（真签 PUT 200 或 GetBucketLocation 出地域）。能盖官方已有对象更稳。

假点：InvalidAccessKeyId；只能传到固定前缀；getUploadSign 其实是 SSO 接口没有本地钥；钥过期。密钥实值不进库。单站没中不删短表这行。

和 STS 通配（先申请临时票）、和桶策略对匿名全开（不用钥）、和 viewer XOR 藏 COS 永久钥（要解开再问 AccountId）都不是一条：本条是 **webpack 明文永久钥 + 前端自己算签**。

### 桶策略对匿名全开（短表有指针）

认：官网/控制台的图、使用指南、协议直接挂在 OSS / cloudrun 一类桶域名上；桶根或 `?policy` / GetBucketPolicy / 等价策略接口能拉开，语句是全 Allow。

打：

1. 策略能看就看；再对桶做 LIST（无 AK）  
2. 对**已经在官网上引用的对象**试 PUT / 覆盖（不要去改桶策略本身）  
3. 指南、协议、站点图优先；盖完用原来的官方 URL 打开验收  

算成：官方那份指南/协议/图的内容变成你传的。只证明匿名能 LIST、或只能传到一个没人引用的新 key → 假点。

假点：策略只读不能写；PUT 只能落自己前缀；下到的本来就是公开静态页。单站没中不删短表这行。

和 STS `*`（要先申请凭证、key 打成通配）、和 filename `../` 穿越租户目录、和 Azure 容器级 SAS 都不是一条：本条是 **桶策略对匿名放开，不用凭证**。

### 存储代理 sign key=/（短表有指针）

认：业务网关把对象存储代理成 `/api/storage/sign`（或同类 sign），query 只吃 `key`。`key=/` 或 `key=.` 回 S3 `ListBucketResult` XML，不是申请 STS。

打（不登录）：

1. GET `?key=/`（再试 `.`）。对照乱填 key 应 `NoSuchKey` / 400  
2. 列表里抄业务前缀（`images/` `editor-` 一类）再 GET 同一口  
3. 看对象是不是未公开素材，不要停在官网 Banner  

算成：列出并读到他人未公开对象原文。

假点：只有 app-static 公开静态；`filename=` 400 当没口。单站没中不删短表这行。和 STS 通配（先领钥）、桶策略匿名全开（直打桶域）不是一条：本条是 **业务网关自己当 List/Get 代理**。


### 制品下载详情把 uin 有无当登录闸（短表有指针）

认：软件/专有云/物料下载中心；详情 JSON 有 `DownloadURL`；前端从 Cookie 抄 `uin`/`skey` 拼 query。空身份时 URL 是空串、页面跳登录。

打：不登录 GET 详情，身份字段填非空假值（`uin=1`），不要 skey。对照空 uin。拿回的带签 URL Range GET 前几十字节看 ELF/PK。

算成：专有云安装包/内部部署文档真文件。空 uin 也出 URL → 完全无鉴权（另一条）。带签 403 / 只有公开说明书 → 没成。

### 入驻 JS 写死 fileKey（短表有指针）

认：入驻/资质 SPA 打包 JS 的 mock 或演示 formData 写死一长串密文 `fileKey`。站点根 301 到新域，**旧 host 下载口可能还活**。不要把 mock 当占位丢掉，也不要把 301 当整站废。

打（不登录）：

1. 跟新域 chunk 抄 `fileKey`  
2. 打旧 host `/json/view/file/downloadFile?fileKey=`（或同类）  
3. 对照：乱填 fileKey 应空/错，真 key 出图  

算成：私有桶执照/证件原图真下到。

假点：把 301 新域名当整站废；mock fileKey 当下占位且乱填也出同一张图。单站没中不删短表这行。密钥实值、完整 JS 不进本篇。

### 分享鉴权 false 仍下媒体（短表有指针）

认：云录制分享；鉴权接口有 `download_enable`/`view_minutes_enable`。或会议 JSON 网关根本没有 `permission/auth`（404 别停）。

打（不登录）：

1. `download-multi-record-file` **和** `sign-multi-record-file` 都打（要 `auth_share_id`+`resource_type`）。国际 JSON 网关缺 `sharing_id` 只回 `2710500 参数非法`，`auth_share_id` 和 `sharing_id` 一起带才签发 MP4；缺了会当没洞。**POST JSON 报「录制 id 不能为空」别停，改 GET query 把 record_id / auth_share_id 放进 URL。**  
2. 没有鉴权口不要当成没入口：直接打 `public/record-detail/download-multi-record-file`。  
3. 纪要/时间线 `get-full-summary` / `query-timeline` 只填 `record_id` 也试，不要默认必须带 share。  
4. COS 无 Referer 的 403 **不是终点**：带分享页 Referer 再 GET。  
5. `permission/get-cfg` 看会不会吐同会其它 record。  
6. 只拿到 url 没 GET 到 MP4 算半条，继续跟。  

算成：鉴权写 false 仍拉到真 MP4（ftypisom+体积）；或只要 record_id 出纪要全文（不是标题）。

假点：鉴权真拦了、下不到文件；只有公开说明书；纪要只要标题没有正文。单站没中不删短表这行。

### 密码分享回包带明文提取码（短表有指针）

认：分享详情 JSON 一边 `need_pwd` / `auth_level`（或同类）表示要提取码，一边 auth 对象把明文提取码放进 `pass_word`（或同类）。或落地 HTML / `syncData` 内联同一明文码。

打（不登录）：

1. 先空着提取码打查看口。对照：文件列表应空，闸字段应是要码。  
2. 同一份回包里抄明文码，填回查看口。对照：空密时列表空、填了才出 `file_id`。  
3. **落地 HTML / `syncData` 里已经有明文 `pass_word` 就直接抄**，不必先打 View CGI。  
4. 拿 `file_id` 和这份码打下载口，跟到真文件头（PDF/ZIP 一类正文），不要停在 JSON 有码。

算成：拿到提取码并下到密码分享正文，不是空密直接出文件列表。

假点：`pass_word` 是哈希抄了登不进；空密 View 已经出文件（那是无提取码分享，不是这枪）。单站没中不删短表这行。
密钥实值、完整 JS 不进本篇。


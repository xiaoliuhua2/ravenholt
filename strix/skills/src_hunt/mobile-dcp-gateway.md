---
name: "mobile-dcp-gateway"
description: "运营商「dcp / 集中运营」类小程序加密网关（2026-09-17 四川移动实证）"
---

> **ravenholt 环境版**：本文件由 `scripts/vendor_src_hunt.py` 按 `profiles/ravenholt.yaml` 生成。
> 技能一律用 `load_skill("src_hunt/<name>")` 按名加载，正文里的旧文件路径只作索引；
> `01`～`10` 指 `src_hunt/0X-*`。旧环境路径/工具名已替换；正文点名的脚本在沙箱里不存在时，改用等价工具，不要停工。

# 运营商「dcp / 集中运营」类小程序加密网关（2026-09-17 四川移动实证）

> **触发**：目标站是小程序 / APP，请求体是 `{"body":"<base64密文>","secRamSt":"<base64密文>"}`，响应是 `{"body":"...","key":"..."}`，
> 且路径里成片出现 `/pub/`、`api-ap-xxx-buss`、`getFork`。
> **一句话**：这层"加密+签名"对攻击者零防护，掏空它之后**洞在 `/pub/` 前缀里**。

## 0. 三十分钟做完的事（顺序别乱）

```
1) 解包小程序 → 找 $http 封装 → 抄出算法（这一层是平台级的，抄一次终身受用）
2) 用 沙箱内 Python 脚本 自造合法请求（能发出去 + 解回响应 = 大门打开）
3) 静态抽全量 API 映射表（几百条）→ 挑只读接口
4) 批量「不带 Authorization + 空参」扫一遍 → 按回码分三类（登录闸 / 公开面 / 缺参可达）
5) 对「缺参可达」逐个补参 → 找那些**吐内部数据的 /pub/ 口**
6) 找到吐身份/名单/号的口 → 再看有没有第二个口能从它吐出的标识再换一份敏感数据（链）
```

## 1. 掏空网关（算法）

```
GET  <host>/api-ap-user-buss/pub/commonality/getFork        ← 未授权，白送一对 1024 位 RSA 密钥
     resp.body = {prFork, puFork, uuid, timestamp}

# puFork/prFork 不是直接可用的 PEM，先解一层：
f(x):  e = AES-ECB-PKCS7-dec( base64_decode(x), key="sDKgjtBWBewITfst" )
       r = e[-4:][:2]; n = int(r[0]); i = int(r[1])
       o = e[:-4]; a = e[-2:]
       return o[:n] + o[n+i:] + a          # 把尾部编码的两段插回中间
setPublicKey(f(puFork)); setPrivateKey(f(prFork))   # puFork 加密请求 / prFork 解响应

POST 业务请求：
  body      = encryptLong(json.dumps(payload))      # 分块 PKCS#1 v1.5，块长 = keylen-11，**输出 Base64**
  secRamSt  = encrypt(random16 + "_" + 毫秒时间戳)
  sign      = md5(body + "U&6@2XekcRBtNPHc")        # 盐硬编码在前端
  headers   = Authorization(可空) / Fork=getFork.uuid / sign / TIMESTAMP=getFork.timestamp

响应：
  aesKey = decryptLong(key)                          # 用 prFork
  plain  = AES-ECB-PKCS7-dec(base64_decode(body), aesKey)
  plain  = encodeSearchKey(plain) → decodeURIComponent → JSON
```

**判断要点（省时间）**
- **请求体解不开是正常的**：只服务端有对应私钥。**别在请求体上耗**，直接看响应。
- `decryptLong` 要同时兼容 hex / base64：`t.length > 2k` 才分块，否则单块；块按 `2k` 十六进制右对齐。
- 服务端 **收 Base64，不收 hex**。Py 侧用 `int.from_bytes` + `pow` 自实现 PKCS#1 v1.5，别指望现成库输出格式对上。
- 一旦能吃透响应，"能不能造请求"这一步就过了：**签名盐在前端 + 密钥对由未授权接口白送 = 签名不构成访问控制**。
  剩下的唯一身份载体是 `Authorization: bearer <access_token>`（登录接口下发，注意 `expires_in`，四川移动是 2591999 秒≈30 天 —— 顺手记一笔"长效凭证"）。

## 2. 洞在哪：`/pub/` 前缀的内部数据口

网关把所有接口按业务域切成 `api-ap-<域>-buss`，**公开面几乎全带 `/pub/`**，需要登录的反而**不带** `/pub/`（如 `/api-ap-service-buss/user/getCmUserInfo` 无 auth 回 40001）。
所以扫描时的分类读法：

| 未登录、空参回包 | 含义 | 动作 |
|---|---|---|
| `40001 用户获取认证信息失败` | 登录闸，正常 | 放掉 |
| `0 成功` + 数据 | **公开面** | 逐个看字段，是否符合"公开"的定义 |
| `400 参数错误：[X 不能为空]` | **可达但缺参** | ★ 补参再打，最容易出洞的一类 |
| `404` + 加密兜底体 | 路径不存在/已下线 | 记掉 |
| `1000 xxx不能为空` / `500 数据格式错误` | 应用层参数校验 | 同上，补参 |

**四川移动实测（★ 先看这条反面教材，再看下面）**

一开始把这三个口判成"高危未授权泄露员工手机号"并落了报告：

| 口 | 未登录 | 拿到了什么 |
|---|---|---|
| `/api-ap-user-buss/pub/getAllStaffInfoByHallNo2` | ✅ | `{lat,lng,pageInfo,staffName:"",hallNoList:[厅店号]}` → 员工 `staffCode`(明文工号) / `staffName`(脱敏) / `staffPhone`(脱敏) / `headUrl` |
| `/api-ap-data-common-buss/pub/geo/getAllChannelByCity2` | ✅ | 全省 **84139** 个厅店（名称/地址/经纬度/**厅店号**）|
| `/api-ap-user-buss/pub/getPhone` | ✅ | `{type:2, staffCode: <固定 RSA 公钥加密工号>}` → **明文手机号**；`{type:1, hallNo: <密文>}` → 厅店电话 |

**结果：撤稿。** 回读调用点所在**页面**才发现这是产品的公开业务链路：
- `getAllStaffInfoByHallNo2` 用在 `pages/tab_nearby_store/COMPO/tab-n-s-manager.js`，宿主页是 **tabBar 一级「附近厅店」**，页面无登录守卫；
- `getPhone` 用在两处：① 同一组件列表项的「拨号」按钮；② **商品详情页的「咨询营业员」按钮**（`app-service.js` @1271947，props 带 `subBtnText:"预约登记"` / `isShowPhone`）：
  ```js
  e = privateBusinessHall.staffCode
      ? {staffCode: $jsfun.encrypt(privateBusinessHall.staffCode), type: 2}   // 拨员工
      : {type: 1, hallNo: $jsfun.encrypt(privateBusinessHall.hallNo)};        // 拨营业厅
  $http.post($api.getPhone, e).then(e => $utils.callPhone(e))                 // wx.makePhoneCall
  ```
- 组件里还用 `managerInfo={headImg,name,shop,phone}` 生成「客户经理名片」图片。

→ 号码必须下发客户端才能拨号，**不存在"本该鉴权而没鉴权"**，属 `03` 报告规则的"本职可读 / 公开运营数据 → 不写"。
`staffCode` 也一样：在名片/二维码（`getQwUserQrCodeByStaffCode`）场景里本来就对外。

### ★★ 因此多一道闸（比"未授权"三条闸更前一步）

> **判"未授权/越权"之前，先答一个问题：这个数据在产品里是不是本来就给未登录用户看的？**
>
> **`/pub/` 未鉴权 ≠ 越权。** 反证只有两个地方找得到，缺一不可：
> 1. **调用点所在的页面** —— 是 tabBar 一级页 / 首页 / 商品详情这类公开页，还是 `我的`/`店铺管理`/后台这类登录后页？
>    找法：在解包 JS 里搜接口名，往前后扩 9KB 抓 `currentFile:'pages/...'`（uni-app 的页面归属标记）。
> 2. **按钮语义** —— "拨号/咨询/预约/联系" 这类动作意味着下游必然拿到真实号码；"查看/管理/导出/统计" 才可能是内部数据。
>
> 只看到"未登录也能返回 200 + 有脱敏字段"就写报告 = 会撤稿。

**通用线索（保留）**：还是那两条 —— ① 有未授权口吐「工号 / 厅店号 / 员工ID」这类内部标识，就去清单里搜以它为入参、回包带手机号/身份证的接口；
② 脱敏字段在列表口、明文在另一个口，是这类站的常见配法。**但命中之后必须在上面那道闸里过一遍再写。**

上表那三个口仍值得记：**它们是"公开数据可枚举"的典型**（可按任意 `hallNo` 批量拉、`hallNoList` 还是数组），
如果客户在意抓取，可给"按定位的厅做白名单 + 频率限制"的加固建议，**但不构成漏洞报告**。


### 2.1 前端固定密钥那一套（别单独当洞写）
小程序里常另有一把固定 RSA 公钥（四川移动在模块 `9f21` / `$jsfun.encrypt`）用于给 `getPhone`、`wxMiniSmsLogin`
的工号 / 手机号 / 验证码参数加密。**服务端只收密文，明文回"获取手机号失败"**。
另外手机号字段常有固定 AES（key `sDKgjtBWBewITfst`、iv `8327677658416237`，CBC）可还原 `encryptionPhone`/`aesStaffPhone`/`referencePhone`。
按报告规则（`03` 的"不写"表）：**单纯的手机号加解密钥不写报告**，只作为链路里的加密手段写进复现步骤。

## 3. 已证伪清单（同类站可直接跳过）
- 订单详情换邻近 orderId / 换 contactCode → `1000 用户权限校验没通过`（归属校验正常）
- 佣金、分销、校园、权益类 `/pub/` 口未登录 → 40001
- 图形验证码 `/api-ap-web-center/captcha` → 只回图片 base64 + 服务端 token，**无答案回显**
- 厅店/网点目录里的 `phone` 字段 → 抽样 300 条 297 条打码，**掩码到位，别写**
- `getToken`（`/api-ap-user-buss/put/authentication/getToken`）→ 返回 `YZsidssolg<40hex>`，
  每次随机且打本网关一律 40001，**只是给 COC 平台的跳转票据**，不构成身份（但可记"生产凭证被明文拼进 URL 传给 dev 域"这类加固项）

## 4. 工具
`沙箱内 Python 脚本`（`HOST` 可用 `DCP_HOST` 环境变量换站）：`Session().refresh()` 取钥 →
`call(path, payload)` 发请求 → `call_json()` 直出明文 JSON；`jsfun_encrypt_b64()` 打固定公钥那套；
`last_packet` 现成的可粘贴整包。整包生成 + 原样重放验证见任务 `tmp/sc_packets.py` 思路。

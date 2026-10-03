# 一扫开店 / Snap2Order — 可转发运行包

这是一份干净代码包，不含原作者的账号、菜单、订单、数据库或 API 密钥。首次启动会自动建立空数据库，每位商家注册自己的小店，顾客扫码后无需注册即可点单。

## 朋友拿到后怎么运行

1. 完整解压 ZIP，保持目录结构。
2. 电脑安装 **Python 3.11 或以上版本**。下载：https://www.python.org/downloads/ 。Windows 安装时勾选 Add Python to PATH。
3. Windows 双击 `Start.bat`；macOS 双击 `Start.command`；Linux 执行 `sh start.sh`。
4. 浏览器自动打开 `http://localhost:8765`，保持启动窗口打开；Ctrl+C 停止。

二维码库已经随包附带，不需要 pip/npm，不需要 macOS OCR，也不需要复制原作者的 Python 安装目录。若 macOS 双击无法执行，可以在终端进入解压目录运行 `python3 launcher.py`。

仅运行基本流程不需要配置密钥：注册商家 → 手动添加或显式载入演示菜单 → 逐项确认 → 发布 → 顾客点单 → 模拟支付 → 商家处理订单。演示菜单故意保留“红油抄于”，可改为“红油抄手”。

## 想把运行环境也自动准备好

安装 Docker Desktop 后，在解压目录运行：

```sh
docker compose up --build
```

它根据 `Dockerfile` 准备 Python 3.12 环境和完整服务，访问 `http://localhost:8765`。首次构建需下载官方 Python 镜像，因此需要网络。数据库放在持久化卷中，正常重启保留数据。停止：`docker compose down`，不要加 `-v`，否则会删除数据卷。

本次已在本机 Python 下验证；Windows 启动脚本、Docker 容器及真实手机尚未实际运行验收。

## 已实现的页面与隔离

- `/login`：**商家专用**注册登录，没有顾客身份选择。
- `/merchant/menu`：上传、拍照、识别、菜单确认、发布与分享二维码。
- `/merchant/orders`：本店商家的独立接单工作台。
- `/shops`：选择已开业的小店。
- `/s/店铺ID`：固定的单店点餐链接，顾客无需注册。
- `/customer/orders`：本设备的匿名顾客订单。

每店具有固定独立链接和网页二维码，菜单更新后链接不变。顾客不进入商家后台。商家与匿名顾客使用独立会话，商家可预览顾客点餐，不必先退出商家账号。

顾客订单依浏览器会话隔离。清除 Cookie、换浏览器或换手机不能找回匿名订单；同一共享设备的同一会话可看到本设备历史。商家仍可在自己的后台查看收到的订单。正式小程序可通过微信身份绑定来实现顾客跨设备找回。

## 手机怎么使用、二维码怎么分享

电脑和手机在同一个 Wi-Fi：在手机访问 `http://电脑局域网IP:8765`，电脑保持服务运行。防火墙需要允许本地端口。用局域网 IP 打开商家页面后，二维码会指向该地址。`localhost` 指手机自身，不能把电脑 localhost 链接直接发给另一台手机。

让异地朋友手机都能使用：把前后端一起部署到公网服务器、绑定 HTTPS 域名，在服务器 `.env` 配置：

```dotenv
PUBLIC_URL=https://你的域名
COOKIE_SECURE=1
HOST=0.0.0.0
PORT=8765
```

`PUBLIC_URL` 是最终访问域名，不应填写路径、末尾斜杠或 localhost。生成的链接和二维码会使用它。服务器只有静态网页不能运行登录、订单或 OCR 服务，必须运行 Python 后端。`deploy/nginx.conf` 为 HTTPS 反向代理参考配置。

## 相机与访问权限

网页“手机拍照”先显示拍照说明，点击“开启相机”后才向浏览器请求摄像头权限，不申请麦克风。拒绝后显示恢复说明，可从相册选择。关闭相机或离开页面时停止摄像头。

网页实时摄像头需 HTTPS 或 localhost 安全上下文；局域网 HTTP 可能不能直接打开，界面提供“改用系统相机”入口。具体弹窗由浏览器/微信/操作系统控制，网页不能替用户授予权限。

## 外部 OCR 配置

手机 → 你的服务器 `/api/merchant/ocr` → 云端视觉识别 → 菜名/价格/分类 → 商家人工确认。

将 `.env.example` 复制为 `.env`，只在服务器填入自己的 OCR.space API Key，重启服务：

```dotenv
OCR_PROVIDER=ocrspace
OCR_API_KEY=自己的OCR.space_API_Key
OCR_PROVIDER_LABEL=OCR.space
OCR_API_URL=https://api.ocr.space/parse/image
OCR_LANGUAGE=chs
OCR_ENGINE=2
OCR_MAX_IMAGE_BYTES=950000
```

[申请 API Key / 官方接口说明](https://ocr.space/ocrapi)。默认使用简体中文 chs，可改 cht 或 eng。服务端 HTTPS POST 上传 Base64 图片，Key 仅置于请求头，返回文字/坐标后按同一行规则配对菜名和价格。所有项目未确认；OCR.space 不返回菜品识别置信度，本版不会伪造置信度。分类由本地规则推断。

免费套餐图片上限 1MB，本版自动压缩到 950KB 以内；较大菜单建议裁剪后拍摄，过度压缩会降低文字清晰度。有其他套餐可调整上限和对应 API URL。时价留空，由商家填写。复杂多栏、多个规格价格的菜单仍可能配对错误，必须人工确认。

未配置、无效 Key、额度/网络错误、无法配对时明确报错，图片仍保留，可手动录入；不会使用演示数据冒充识别成功。没有配置有效 Key，本次仅验证模拟响应与接口协议，不宣称真实图片识别通过。

保留旧视觉模型适配器：需要时将 OCR_PROVIDER 改为 vision，同时更换相应 API Key、OCR_API_URL、OCR_MODEL 和 OCR_PROVIDER_LABEL。默认无需视觉模型服务。

## 微信小程序

**当前可直接运行的是网页服务。** `miniprogram/` 另外包含原生顾客端源码：店铺列表、扫码进入单店、购物车、免注册下单、模拟支付和订单。商家仍通过网页管理；尚未完成完整的原生商家页面。

微信开发者工具导入 `miniprogram/`，填写 AppID 和合法 HTTPS 后端域名，详见该目录 README。`USE_WECHAT_LOGIN=false` 使用匿名顾客会话；配置为 true 后使用 wx.login → 后端 code2Session → 自有登录态，无需注册账号密码或获取手机号。

服务器另外配置（仅存在服务器）：

```dotenv
WECHAT_APP_ID=你的小程序AppID
WECHAT_APP_SECRET=你的小程序AppSecret
WECHAT_CODE_ENV=release
```

- `/api/auth/wechat`：接受临时 code，绑定微信顾客身份，签发自有 token，不下发 AppSecret/session_key。
- `/api/merchant/minicode`：生成单店小程序码；scene 为店铺 ID，进入 `pages/menu/index`。
- `/api/merchant/qrcode`：已可用的网页 SVG 二维码，与小程序码是不同入口。
- `miniprogram/utils/menu-camera.js`：原生 wx.chooseMedia 相机/相册与权限错误恢复适配，供原生商家页使用。

真实微信登录、小程序码、权限弹窗和真机行为仍需有效 AppID、平台配置与开发者工具验收，未在本次验证中宣称通过。无真实微信支付。

## 数据库与备份

SQLite `data/snap2order.sqlite3` 自动创建，WAL 模式、外键、事务、schema 版本 2。用户、会话、店铺、菜单、订单、订单快照、OCR 来源、限流和微信身份均持久化。

服务端每次检查账号归属，订单金额使用整数分计算。改价不影响历史订单；顾客端价格已变化时要求重新确认；提交编号防止重复下单。商家密码加盐 PBKDF2-SHA256 存储。

不要在服务运行时只复制主数据库而遗漏 WAL，使用在线备份：

```sh
python3 backup.py /你的备份目录/backup.sqlite3
```

多实例或较大规模上线建议迁移 PostgreSQL，并将私有图片迁移到对象存储。本版仅用于演示和小范围试用，尚无密码找回、短信、生产运维或完整隐私合规流程。

## 验证

```sh
python3 -m unittest -q test_app.py
```

22 项测试已通过：账号鉴权、顾客免注册会话、商家与顾客隔离、订单状态、订单快照、价格变化、防重复提交、二维码、私有图片、OCR 成功/失败适配和微信身份复用。测试使用临时数据库与模拟供应商响应，不调用真实收费接口、不改当前业务数据库。

运行包另外进行了解压后独立启动、创建空数据库和注册/点单检查，具体记录见 `验收记录.md`。


### 启动及 OCR 修复（2026-10-03）
双击 Start.command：端口被占用时自动选择下一个可用端口，并打开对应网页。终端会显示当前目录和 OCR 配置状态。API Key 请填在 `.env`；首次误填 `.env.example` 时会自动迁移至 `.env`，已有 `.env` 优先。修改配置后重启服务。包内提供 Mozilla 根证书，Python 未安装系统证书也可安全访问 HTTPS，证书验证始终开启。OCR Engine 2 默认自动识别语言。


### 菜品图片
商家编辑每道菜时可上传实拍、拍照、选推荐插画或暂不放图。照片在浏览器压缩至最长边 1600 像素、2MB 以内，上传至自己的店铺并随 SQLite 数据库备份；没有图片也可以发布。素材库内置六类原创插画，按菜名和分类推荐，顾客页标记“素材示意图”。图片选择需保存草稿或发布，草稿照片只对所属商家可见，发布的上架菜品照片可供顾客浏览。取消图片后重新发布即可停止公开展示。已有数据库启动时自动升级到版本 3，保留账号、菜单和订单。商家预览完整缩放原图，顾客菜单维持原有缩略图。小程序图片 URL 已接入（未在真机测试）。

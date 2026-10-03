# 微信小程序顾客端源码

当前包含店铺列表、扫码进入单店、购物车、免注册下单、模拟支付与顾客订单。商家管理仍使用网页；`utils/menu-camera.js` 提供原生小程序拍照/权限拒绝恢复适配，尚未接入完整小程序商家页面。

微信开发者工具导入此目录，将 project.config.json 的 touristappid 改为你的小程序 AppID。config.js 的 API_BASE 改为你的公网 HTTPS 后端域名，并在微信后台配置 request 合法域名。localhost 仅能用于电脑开发者工具测试，不能用于另一台手机。

config.js 的 USE_WECHAT_LOGIN=false：后端匿名顾客会话，无需注册密码。true：调用 wx.login 获得 code，后端 /api/auth/wechat 换取 openid 并签发自有 token；服务器必须配置 WECHAT_APP_ID / WECHAT_APP_SECRET。不索取手机号、昵称或头像；AppSecret 和 session_key 不下发。

每店唯一 store ID，分享页面路径 `pages/menu/index?store=店铺ID`。后端 `/api/merchant/minicode` 生成小程序码，其 scene 为店铺 ID；小程序页面读取 scene，直接进入对应菜单。该接口需有效账号和 AppID 配置；网页 SVG 二维码与小程序码是两种入口。

未运行微信开发者工具或真机验收。发布前需配置微信平台要求的隐私声明、合法域名、相机相关权限说明并检查原生权限弹窗。模拟支付不会调用 wx.requestPayment。

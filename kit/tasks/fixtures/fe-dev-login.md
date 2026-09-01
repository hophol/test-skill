# 前端技术方案 —— 登录功能

## 组件树

- LoginPage（容器）
  - LoginTabs（展示：页签切换）
  - PasswordForm（展示：账号/密码表单）
  - SmsCodeForm（展示：手机号/验证码表单）
  - AgreementBar（展示：协议勾选 + 抖动提示）

## 状态设计

- global：userInfo（登录成功后写入，触发全局刷新）
- local：activeTab（当前页签）、countdown（验证码倒计时秒数）、submitting（防重锁）

## API 对接

- POST /api/login {account, password} —— 成功返回 token；423 = 账号锁定
- POST /api/sms/send {mobile} —— 发送验证码
- POST /api/sms/login {mobile, code} —— 验证码登录
- loading / error 处理统一收在 LoginPage 容器层，表单组件只抛事件

## 路由与目录

- 新增路由 /login，来源页跳转逻辑放路由守卫
- 目录：src/pages/login/，组件就近放置

## 风险点

- 锁定逻辑依赖后端错误码 423，前端只做提示展示，不本地计数
- 倒计时组件与页签切换的卸载竞态需要处理

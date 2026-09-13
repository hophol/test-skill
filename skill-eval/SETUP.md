# skill-eval（DSH 引擎）环境说明

这是 cc-eval 的姊妹实现：同一套评测思想，换成 DSH（DeepSeek Harness）作为被测引擎。
**需要在装有 DSH 的机器上运行**，且有两处机器相关配置：

1. `overlay.yml` 里 `skill-eval-runner` 的 `name: file:///D:/.../plugin/index.mjs`
   是绝对 file URL —— 克隆后改成你本机的插件路径。
2. `plugin/index.mjs` 依赖 `@deepseek-ai/*` 包：在 `plugin/` 下建一个指到 DSH 安装目录的
   junction，例如（Windows）：

```powershell
New-Item -ItemType Junction -Path plugin\node_modules -Target <DSH安装目录>\node_modules\@deepseek-ai\dsh\node_modules
```

运行方式（详见 `MANUAL.md`）：

```bash
node oracle.mjs
node run.mjs --repeats 3
node report.mjs
```

DSH 相关事实（为什么这个引擎要单独实现）：原生 headless 一次只提交一条用户消息、
且没有挂 `ask_user_question` 工具，多轮与提问链路必须由替换 `headless-runner` 的插件补齐。

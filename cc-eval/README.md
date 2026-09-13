# cc-eval — 在 Claude Code 里评测 skill 的执行过程与结果

> 完整能力说明见 **[`SPEC.md`](SPEC.md)**；每一步改动记录见 **[`CHANGELOG.md`](CHANGELOG.md)**。

它**不给 SKILL.md 文本打分**，而是让同一次脚本对话跑两遍——一遍工作区里**装着 skill**，一遍**删掉 skill**——
然后对**过程**（每一轮调了哪些工具、有没有真的加载 skill、有没有先问再动手）和**结果**（磁盘上留下了什么、内容对不对）做断言。

```
cc-eval oracle                 # 判据自检（0 token）：正向控制 + canary 负向控制
cc-eval run [caseId] [--repeats N] [--concurrency N] [--arms with_skill,without_skill] [--model M]
cc-eval report                 # 聚合全部历史运行 → out/summary.json + benchmark.json
```

退出码只回答一个问题：**"有 skill 那一臂是否符合要求"**（外加 canary 必须挂）。基线失败是**预期结果**——那就是 lift。

## 它是怎么驱动 Claude Code 的

每一轮起一个独立进程，全程共用**一个会话**：

```
turn 1 : claude -p "<第一轮>" --output-format stream-json --verbose [--permission-mode acceptEdits]
         └─ 从 system/init 或 result 事件里取 session_id
turn N : claude -p "<第 N 轮>" --resume <session_id> --output-format stream-json --verbose
```

- **stdout 直接重定向到文件**（不用管道：`stdio: ['ignore', fd, fd]`），既避免大流被截断，也能在没有管道的沙箱里跑；
- 事件流（NDJSON）被归一化成"轮视图"：`toolCalls[{name,input}]`、`assistantText`、`usage{input,output,cacheRead}`、`costUsd`、`numTurns`、`observedModels`、`permissionDenials`、`sessionId`；
- **skill 是否生效**的判据：assistant 事件里出现 `tool_use` 且 `name === "Skill"`、`input.skill === "<skill 名>"`（后面会跟一条 `tool_result: "Launching skill: <name>"`）。

## 用例格式（`cases/*.json`，`cases/INDEX.txt` 是清单）

```jsonc
{
  "id": "clarify-multiturn",
  "workspace": "<夹具工作区绝对路径>",      // 里面有 .claude/skills/<skill>/SKILL.md
  "artifacts": ["plan.md"],                  // 夹具卫生：跑之前这些文件必须不存在
  "oracle": { "plan.md": "platform: ...\n" },// 判据自检用的"标准产物"
  "slots": { "platform": { "answer": "阿里云 ECS" } },   // {{platform}} 展开到用户轮次
  "timeout_ms": 240000,
  "turns": [
    { "user": "帮我把 demo-app 发布上线",
      "assert": { "must_ask_user": true, "forbid_tools": ["Write","Edit","Bash"] } },
    { "user": "平台用 {{platform}}，{{deadline}} 之前必须上线",
      "assert": { "must_write_file": "plan.md", "must_contain_file": ["阿里云 ECS"],
                  "must_not_reask": ["平台","截止","deadline"] } }
  ]
}
```

断言（按轮）：

| 断言 | 判据 |
|---|---|
| `must_call_skill` / `must_not_call_skill` | 本轮有没有 `Skill` 工具调用、是不是期望的那个 skill |
| `must_ask_user` | `AskUserQuestion` 调用**或**回复里带问号（宽松：宁可算它问了） |
| `must_not_ask` | **只认 `AskUserQuestion` 工具调用**（严格：避免把"需要我继续吗？"误判成追问） |
| `must_not_reask` | 问句里是否又提到已确认的槽位关键词（子句级判定） |
| `forbid_tools` | 本轮不得出现列出的工具（如 `Write/Edit/Bash`） |
| `must_contain` | 本轮回复必须包含的字符串 |
| `must_write_file` + `must_contain_file` | 产物存在且包含全部字符串（世界状态） |

## 实测（本机 Claude Code 2.1.170，各 1 次）

```
ping-skill        with_skill  1/1 PASS  turns=1  wall= 6.8s  $0.123   tools=[Skill]
                  without     0/1 FAIL  turns=1  wall=35.3s  $0.094   tools=[Bash×4]      lift=1
clarify-multiturn with_skill  1/1 PASS  turns=2  wall=27.3s  $0.116   tools=[Skill,AskUserQuestion]→[Write,Read]
                  without     0/1 FAIL  turns=2  wall=67.3s  $0.165   tools=[Bash,Glob,AskUserQuestion]→[Bash]  lift=1
canary-never      with_skill  0/1 FAIL（应当失败）      wall= 4.0s  $0.022   canary=ok
macro lift = 1 | total cost = $0.52
```

产物：每次运行 `out/runs/<case>.<arm>.run<k>/{report.json,grading.json}`；聚合 `out/summary.json` + **Anthropic skill-creator 兼容的 `benchmark.json`**（`run_summary.{with_skill,without_skill,delta}`）。

## Claude Code 上的硬事实（实测）

1. **skill 是显式工具**：`Skill` 在 `--output-format stream-json` 的 init 事件里；调用形如 `{"skill":"ping-check","args":"..."}`，紧跟一条 `tool_result: "Launching skill: ping-check"`。
2. **`AskUserQuestion` 在 `-p` 模式下是死路**：工具调用会返回一个占位 `tool_result: "Answer questions?"`，拿不到真实答案 —— 所以提问型 skill 必须靠**下一轮用户消息**给答案（本 harness 就是这么做的）。这与 DSH 那边"headless 根本没有提问工具"是同一个设计后果。
3. **必须处理权限**：写文件要 `--permission-mode acceptEdits`（默认）或 `--dangerously-skip-permissions`（用例里 `dangerously_skip_permissions: true`）；否则模型会因权限被拒而走偏。
4. **一轮= 一个进程**：多轮靠 `--resume <session_id>`，轮内 `num_turns` 可能 >1；事件流里有大量 `system/thinking_tokens` 噪声，解析时按 `type` 过滤即可。
5. **可观测成本与路由**：`result` 事件带 `total_cost_usd`、`usage{input,output,cache_read}`、`num_turns`、`duration_ms`、`permission_denials`、`modelUsage`（键名就是**实际用的模型**——本机走的是 `glm-5.3`）。报告里同时记 `requestedModel` 与 `observedModels`，避免"我指定了模型"被当成"真用了这个模型"。

## 评测实现上的两个教训（今天真踩到的）

1. **"有没有提问"不能用一个宽松判据同时管两件事**。最初 `must_not_ask` 也用"回复里有问号"，结果模型在写完 plan.md 后礼貌地问了句"需要我继续吗？"就被判失败。修法：`must_ask_user` 宽松（工具或问号），`must_not_ask` 严格（只认 `AskUserQuestion`），再补一条子句级的 `must_not_reask`。
2. **子句级判定的正则会静默地永远为真**。第一版写 `if (!/[?？]/.test(s + '?')) continue`——给每句都补了个问号，等于每条断言都命中。改成 `text.match(/[^。！!？?\n]*[？?]/g)`（保留问号本身）才对。

## 与 DSH 版（`../skill-eval`）的关系

同一套评测思想，两个引擎适配器：`skill-eval` 用 DSH 插件 + 会话事件流；`cc-eval` 用 Claude Code CLI + stream-json。
用例 schema、断言库、oracle/canary、统计口径（resolution rate / pass@k / Wilson / lift）都是同一套设计——这正是"换 agent 只换 runner"的落地验证。

## 已知限制

1. 默认只跑 1 次；统计要用 `--repeats 3`（Wilson 区间在 n=1 时几乎没有信息量）；跑批加 `--concurrency 3`（run 级并发，实测 15 任务 166s vs 串行约 8 分钟）。
2. 没有 LLM 裁判层（`judge`）：目前只有确定性断言 + 产物断言。
3. 没有并发（串行），`without_skill` 臂可能很慢（35–67s）。
4. `AskUserQuestion` 的答案无法注入（Claude Code 不暴露接缝），只能靠下一轮用户消息。
5. 尚未跑 CI（`--repeats 3` 全量约 15 次调用、~$1.5 量级）。

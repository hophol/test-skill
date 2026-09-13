# cc-eval 能力说明书（v0.1）

> **这份文档说什么**：我们在 Claude Code 上评测 Agent Skill 的能力是什么、怎么实现、怎么用、结果怎么读、边界在哪。
> **配套**：`README.md`（快速上手）、`CHANGELOG.md`（**每一处改动都有记录**，格式与约定见该文件开头）。
> **适用引擎**：Claude Code（本机实测 2.1.170）。同源的 DSH 版在 `../skill-eval/`，两者的差别只在 runner。

---

## 1. 一句话定义

**它不给 `SKILL.md` 打分。它让同一段脚本对话跑两遍——一遍工作区里装着 skill，一遍删掉 skill——然后对"过程"（哪一轮调了哪些工具、skill 有没有真的被加载、有没有先问再动手）和"结果"（磁盘上留下了什么、内容对不对）做断言，两臂之差就是 skill 的价值（lift）。**

这句话的三个推论：

1. 被评的是**行为差异**，不是文本质量；
2. 判据落在**可观测事实**上（工具轨迹 + 世界状态），不落模型自述；
3. "没有 skill 也能过" 说明**这个用例没有区分度**，不是"skill 没用"。

---

## 2. 为什么要这么设计（约束与取舍）

| 约束（实测） | 后果 |
|---|---|
| Claude Code 的 skill 是**显式工具调用**（`Skill`），不是隐式注入 | 可以确定性判定"skill 是否生效"：`tool_use.name === "Skill"` 且 `input.skill === <名>`，后面跟一条 `tool_result: "Launching skill: <名>"` |
| `AskUserQuestion` 在 `-p`（headless）模式下**拿不到真实答案**，只回一个占位 `"Answer questions?"` | 提问型 skill 必须靠**下一轮用户消息**给答案 → 评测器必须能做多轮 |
| 一轮 `claude -p` 进程结束后进程退出 | 多轮只能靠 `--resume <session_id>` 续同一个会话 |
| 写文件需要权限模式 | 评测要在夹具里显式给 `--permission-mode acceptEdits`（默认）或 `--dangerously-skip-permissions`（用例开关） |
| LLM 有随机性、单次结果不可信 | 报告必须给重复次数、通过率、区间；退出码只对"skill 臂是否达标"负责 |

---

## 3. 架构与数据流

```
cases/*.json + fixtures/<case>/workspace/        用例与夹具（.claude/skills/<skill>/SKILL.md）
        │
        ├─ cc-eval oracle ──────────────────────────────────────────────┐
        │     正向控制：把 case 声明的 oracle 产物写进临时工作区，         │  0 token
        │              文件断言必须能过（证明判据可达）                    │
        │     负向控制：canary 用例的断言必须挂（证明判据会失败）           │
        │                                                                │
        └─ cc-eval run [caseId] [--repeats N] [--concurrency N] [--arms ...] │
              对每个 (case, arm, run)：                                   │
                1) 夹具卫生检查：case.artifacts 不能在夹具里预先存在        │
                2) 复制夹具 → out/ws/<case>/<arm>/run-<k>/workspace        │
                   without_skill 臂：删掉 .claude/ .agents/ .dsh/         │
                3) 逐轮驱动 Claude Code（见 §4），事件写入                │
                   out/runs/<case>.<arm>.run<k>/turn-<i>.jsonl           │
                4) 归一化事件 → 轮视图 → 按轮断言（见 §6）                │
                5) 写 report.json + Anthropic 兼容 grading.json           │
        │                                                                │
        └─ cc-eval report ───────────────────────────────────────────────┘
              聚合 out/*.run<k>.json → out/summary.json
                                    + Anthropic 兼容 out/benchmark.json
              指标：resolutionRate / pass@k / ci95(Wald) / ci95(Wilson)
                    / lift / macroLift / 平均轮数·墙钟·成本·token / canary
```

---

## 4. 怎么驱动 Claude Code（实现细节）

每轮一个进程、全程一个会话，**stdout 直接重定向到文件**（`stdio: ['ignore', fd, fd]`，不走管道）：

```
turn 1 : claude -p "<第一轮>" --output-format stream-json --verbose
             [--permission-mode acceptEdits | --dangerously-skip-permissions]
             [--model <model>]
         └─ 从 system/init 或 result 事件取 session_id
turn N : claude -p "<第 N 轮>" --resume <session_id> --output-format stream-json --verbose
```

**为什么不用管道**：大事件流不会被缓冲截断；同时在没有管道的沙箱里也能跑。

**并发（CC16）**：粒度是 **run（case × arm × repeat）**——轮次在同一 run 内仍串行（共用一个 `--resume` 会话），每个 run 本就有独立工作区副本，无文件冲突；超时用 `taskkill /T /F` 杀整棵进程树（`child.kill()` 杀不掉 agent 拉起的子进程）。实测 15 任务在 `--concurrency 3` 下 **166s**（串行约 8 分钟，≈2.9×），成本持平。
**超时**：每轮 `timeout_ms`（默认 240s），超时记 `timedOut` 并中止该用例的后续轮。
**归一化后的"轮视图"**（断言只吃这个）：

| 字段 | 来源 |
|---|---|
| `toolCalls[{name, input}]` | assistant 事件的 `tool_use` 块 + user 事件的 `tool_result`（以 `<<tool_result>>` 标记） |
| `assistantText` | 本轮最后一条非空 text 块 |
| `usage{input, output, cacheRead}` | `result` 事件的 `usage` |
| `costUsd` / `numTurns` / `durationMs` | `result` 事件 |
| `observedModels` | `result.modelUsage` 的键名（**实际用的模型**） |
| `permissionDenials` / `isError` / `subtype` | `result` 事件 |
| `sessionId` | `system/init` 或 `result` |

> 事件流里 `system/thinking_tokens` 会很密（实测一次 130 条里 122 条），按 `type` 过滤。

---

## 5. 用例格式（`cases/*.json`，清单在 `cases/INDEX.txt`）

```jsonc
{
  "id": "clarify-multiturn",
  "workspace": "D:\\...\\fixtures\\clarify\\workspace",  // 里面有 .claude/skills/<skill>/SKILL.md
  "artifacts": ["plan.md"],                 // 夹具卫生：跑之前这些文件必须不存在
  "oracle": { "plan.md": "platform: ...\n" },// 判据自检用的"标准产物"（canary 用例不写）；多轮用例可用 turn.oracle 按轮声明
  "artifact_patterns": ["**/fe-req-*.md"],  // 变量名产物的夹具卫生（glob）
  "fixture_allowlist": [".claude"],         // 边界用例：除白名单外工作区必须为空
  "slow": true,                             // 慢用例标记（执行型；timeout 已上调）
  "assert": { "must_call_skill_any_turn": "scope-check" },  // 案例级断言（跨轮；skill 会话内只加载一次）
  "slots": { "platform": { "answer": "阿里云 ECS" } },  // {{platform}} 展开进用户轮次
  "timeout_ms": 240000,                     // 每轮超时
  "model": "(可选) --model 覆盖",
  "dangerously_skip_permissions": false,     // true → 传 --dangerously-skip-permissions
  "permission_mode": "acceptEdits",          // 或别的权限模式
  "repeats": 3,                              // 覆盖 CLI --repeats
  "arms": ["with_skill", "without_skill"],   // 覆盖 CLI --arms（canary 只跑一个臂）
  "canary": false,                           // true → 该用例必须失败，通过即判分器损坏
  "turns": [
    { "user": "帮我把 demo-app 发布上线",
      "assert": { "must_ask_user": true, "forbid_tools": ["Write", "Edit", "Bash"] } },
    { "user": "平台用 {{platform}}，{{deadline}} 之前必须上线",
      "assert": { "must_write_file": "plan.md",
                  "must_contain_file": ["阿里云 ECS", "下周五"],
                  "must_not_reask": ["平台", "截止", "deadline"] } }
  ]
}
```

---

## 6. 断言目录（判据）

**过程断言（按轮）**

| 断言 | 判据 | 严格度 |
|---|---|---|
| `must_call_skill: "<名>"` | 本轮出现 `Skill` 工具调用且 `input.skill` 匹配 | 严格（工具级） |
| `must_not_call_skill` | 本轮没有任何 `Skill` 调用 | 严格 |
| `must_ask_user: true` | `AskUserQuestion` 调用 **或** 回复里出现 `? / ？` | **宽松**（宁可算它问了，避免漏判） |
| `must_not_ask` | **只认 `AskUserQuestion` 工具调用** | **严格**（避免把"需要我继续吗？"误判成追问） |
| `must_not_reask: [关键词]` | 把回复按 `。！？\n` 切成子句，**只有带问号的子句**里出现关键词才算重复追问 | 子句级 |
| `forbid_tools: ["Write", …]` | 本轮不得出现列出的工具（Claude Code 工具名首字母大写） | 严格 |
| `must_contain: ["…"] ` | 本轮回复必须包含全部字符串 | 严格 |

**结果断言（世界状态，不看模型自述）**

| 断言 | 判据 |
|---|---|
| `must_write_file: "plan.md"` | 工作区里该文件存在 |
| `must_contain_file: ["…"]` | 该文件内容包含全部字符串 |

**设计原则**：`must_ask_user` 宽松、`must_not_ask` 严格——**同一个词不能用一个判据同时管两件事**（这条是被真实误判逼出来的，见 §10）。

---

## 7. 防自欺机制

| 机制 | 做什么 | 触发后果 |
|---|---|---|
| **oracle gate**（`cc-eval oracle`，0 token） | 正向控制：合成 `case.oracle` 产物 → 文件断言必须能过；负向控制：canary 断言必须挂 | 不通过 → 拒绝该用例，不许跑 |
| **canary 用例**（`cases/canary-never.json`） | 挂一条永远不可能满足的断言（要求写出 `CANARY-NEVER-EXISTS.md`） | 一旦"通过" → `report` 标 `canary: BROKEN`，并让 `run` 退出码非 0：**判分器坏了，整轮数字作废** |
| **夹具卫生检查** | `case.artifacts` 声明的产物不得预先存在于夹具 | 提示 `dirty fixture` 并终止（历史事故：残留 `plan.md` 让两臂都假 PASS，lift=0） |
| **两臂默认都跑** | `without_skill` 是默认臂，不是可选项 | 没有基线就没有 lift，报告会显示 `lift=undefined` |
| **requested vs observed 模型** | 报告同时记请求的模型和 `modelUsage` 里的实际模型 | 避免"我指定了 X"被当成"真的用了 X" |

---

## 8. 结果与产物

**每次运行** `out/runs/<case>.<arm>.run<k>/`：

- `report.json`：`case/arm/run/workspace/sessionId/requestedModel/observedModels/turnsUsed/wallMs/costUsd/tokens{input,output,cacheRead}/skillCalls/passed/failedAssertions/turns[]`
  - 每个 turn：`toolCalls`、`assistantText`、`usage`、`numTurns`、`costUsd`、`permissionDenials`、`timedOut`、`exitCode`、`prompt`、**`assertions[{id, passed, detail}]`**
- `grading.json`：**Anthropic skill-creator 兼容**（`expectations[{text,passed,evidence}]` + `summary{passed,failed,total,pass_rate}`）
- `turn-<i>.jsonl` / `turn-<i>.err`：原始事件流与 stderr（取证用）

**聚合** `cc-eval report` → `out/summary.json` + `out/benchmark.json`（`run_summary.{with_skill,without_skill,delta}`）。

> `grading.json` 与 `benchmark.json` 由 **`../shared/anthropic-artifacts.mjs`** 生成——DSH 引擎版用的是**同一个模块**，两个引擎产物形状一致，可直接喂给 skill-up 等生态工具。
> **canary 用例不计入 `run_summary`**（它按设计必须失败），只在 `cases[]` 里逐条展示，并在 `metadata.canary_cases_excluded` 记数。

指标口径：

| 指标 | 定义 |
|---|---|
| `resolutionRate` | 该臂通过次数 / 运行次数 |
| `pass@k` | 该臂是否至少一次通过 |
| `ci95Wald` | Wald 95% 区间（与 skilljack 同口径；**p=0/1 时退化成退化区间**） |
| `ci95Wilson` | Wilson 区间（极端值下仍诚实，**优先看这个**） |
| `lift` | with 臂通过率 − without 臂通过率（单用例） |
| `macroLift` | 各用例 lift 的宏平均（用例等权） |
| `meanTurns / meanWallMs / meanCostUsd / meanTokens` | 平均轮数 / 墙钟 / 成本 / token |
| `canary` | `ok` = 必挂断言确实挂了；`BROKEN` = 判分器不可信 |

**退出码**：`run` 只回答一个问题——**"skill 臂是否全部达标"**（外加 canary 必须挂、没有 run 被中止）。基线失败是预期结果，不影响退出码。

---

## 9. 实测基线（Claude Code 2.1.170，各 1 次）

```
ping-skill        with_skill  1/1 PASS  turns=1  6.8s  $0.123  tools=[Skill]
                  without     0/1 FAIL  turns=1 35.3s  $0.094  tools=[Bash×4]                       lift=1
clarify-multiturn with_skill  1/1 PASS  turns=2 27.3s  $0.116  [Skill,AskUserQuestion]→[Write,Read]
                  without     0/1 FAIL  turns=2 67.3s  $0.165  [Bash,Glob,AskUserQuestion]→[Bash]  lift=1
canary-never      with_skill  0/1 FAIL（应当失败）  4.0s  $0.022  canary=ok
macro lift = 1 | 合计成本 = $0.52
```

读法：**有 skill 时第 1 轮就 `Skill` 加载 + 按正文行动；无 skill 时它在空工作区里用 Bash/Glob 乱找一圈**——这正是"过程断言"能看见、而只看最终答案看不见的差别。

---

### 9.1 广度轮（CC17 · 2026-09-13，6 个真实 skill，轻用例各 1 次）

```
文档型用例 ×3（需求分析/技术方案/测试设计，内部样本）   with 1/1 PASS，without 0/1  lift=1
frontend-design（纯文本建议型）                          with 1/1 PASS，without 0/1  lift=1
webart（执行型）      with 断言过但 600s 超时（已上调 1200s，待复跑）
链路边界用例（内部样本）  with 0/1，without 0/1           lift=0
macro lift = 0.875（被边界用例拉低）
```

> 内部样本的用例与夹具**不在本公开仓库**，仅私有版本包含；上表保留其结果供口径参考。

**真发现（n=1，待重复验证）**：某个文档型 skill 自称"没有输入就先建议走上游 skill"，但在空工作区 + `AskUserQuestion` 拿不到答案（`-p` 模式返回占位）时，模型**仍自行编造输入并直接产出目标文档**——违反 skill 自己的边界条款。

## 10. 已知限制与踩过的坑

**限制**

1. 默认只跑 1 次；统计要用 `--repeats 3`（n=1 时 Wilson `[0.207,1]`，几乎没有信息量）；
2. 没有 LLM 裁判层（`judge`），目前只有确定性断言 + 产物断言；
3. 串行执行，`without_skill` 臂可能很慢（35–67s）；
4. `AskUserQuestion` 的答案无法注入（Claude Code 不暴露接缝），只能靠下一轮用户消息；
5. 尚未接 CI；全量 `--repeats 3` 约 15 次调用、~$1.5 量级。

**坑（都有记录在 CHANGELOG）**

| # | 坑 | 修法 |
|---|---|---|
| 1 | `must_not_ask` 用"回复里有问号"判定 → 模型写完文件后礼貌问一句就被判失败 | 拆成宽松的 `must_ask_user` 与严格的 `must_not_ask`（只认工具），再加子句级 `must_not_reask` |
| 2 | 子句判定写成 `/[?？]/.test(s + '?')` → **恒真**，每条都命中 | 改成 `text.match(/[^。！!？?\n]*[？?]/g)`，保留问号本身 |
| 3 | 退出码最初把"基线失败"也算失败 | 退出码只对 skill 臂与 canary 负责，基线失败是 lift 的来源 |
| 4 | 报告 `turns` 恒为 0 | `armStats` 读错字段（`numTurns` → `turnsUsed`） |

---

## 11. 路线图

| 优先级 | 事项 | 说明 |
|---|---|---|
| P0 | `--repeats 3` 跑出真统计 | 当前基线只有 n=1 |
| P0 | 把每次改动写进 `CHANGELOG.md` | 见该文件开头的约定 |
| P1 | judge 层 | LLM 裁判只做质量类兜底，确定性断言优先；判分模型与被测模型不同源 |
| ~~P1~~ | ~~并发 + 每 case 独立工作区~~ **已完成（CC16，`--concurrency`）** | run 级并发（case × arm × repeat），轮内仍串行；默认 1 |
| P2 | 失败模式切片 | discovery_failure / instruction_ambiguity / … |
| P2 | CI 接入 | 形态校验硬门 + 通过率门（等 flakiness 基线摸清） |
| P3 | Mock 工具调用 / 会话种子 | 借 agentut 的 mock 与 `initial_session` 思路 |

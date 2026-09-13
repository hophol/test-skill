# Skill 评测能力说明书（skill-eval v0.1）

> 面向对象：要拿这套东西去评自己 skill 的人，以及想把它搬到别的 agent（Claude Code / opencode / codex）上的人。
> 代码位置：`D:\Games\robot\skill-eval\`；原理调研与最佳实践出处见 `D:\Games\robot\skill-eval-research.md`。

---

## 0. 一句话

**它不是"读 skill 文件打分"，它是让同一个 agent 在"有 skill"和"没有 skill"两条世界线上跑同一段对话，再用落在世界状态和工具轨迹上的断言算出差异（lift）。**

---

## 1. 为什么需要自己搭（原生 headless 的两个硬约束）

| 约束 | 证据 |
|---|---|
| 一次性只提交一条用户消息，没有追问面 | 官方 README：`One submitted task only … the runner has no interactive follow-up surface` |
| 连提问工具都没挂 | 实测让模型用 `ask_user_question`，模型回答"当前会话中没有该工具"；`--dump-config` 确认只挂了 `user-questions` 服务，没挂 `dsh-tool-ask-user` 工具 |

所以"多轮对话型 / 提问澄清型"skill 在现成 headless 上根本走不到终点——不是配置问题，是形态问题。

---

## 2. 架构与数据流

```
oracle.mjs        判据自检（0 token，跑批前先跑）
  正向控制：把用例声明的期望产物合成出来，文件断言必须能过
  负向控制：canary 那条不可能满足的断言必须挂
                    |
                    v
run.mjs           批量：cases/INDEX.txt 里的每个用例 × 每个臂 × --repeats N
  1) 夹具卫生检查：用例 artifacts 声明的产物不得预先存在于夹具里
  2) 每个 (用例,臂,第k次) 复制一份独立工作区到 out/ws/<case>/<arm>/run-k/workspace
     - with_skill    : 保留 .dsh/skills/**
     - without_skill : 复制后删掉 .dsh/
  3) 以该工作区为 cwd 启动 dsh 进程
                    |
                    v
dsh --profile skilleval --patch overlay.yml
  overlay：关掉 headless-runner / headless-startup，insert skill-eval-runner
                    |
                    v
plugin/index.mjs  多轮 runner（DSH 插件）
  ① await ctx.get('loader').await()          等树装配完
  ② 挂 dsh-tool-ask-user + 注册脚本化 userQuestions provider（假的"人"）
  ③ agents.create({ sessionId, meta:{cwd}, agentOptions, setup: installModelSelection })
  ④ 逐轮：agent.followup(createUserMessage(...)) → await agent.whenIdle()
  ⑤ 全程 ctx.on('session/event') 收事件，按 event.data.turn 归属到轮
  ⑥ sessions.flush() → 写报告 → appExit(0/1)（+3 秒兜底 process.exit）
                    |
                    v
out/<case>.<arm>.run<k>.json    单次报告（逐轮、逐断言、带证据）
                    |
                    v
report.mjs        聚合全部历史 run → out/summary.json + 控制台表格
                  rate / pass@k / ci95(Wald) / ci95Wilson / lift / macroLift / token / 时长 / canary
```

---

## 3. 实现原理（关键设计点）

### 3.1 用 overlay 把一次性 runner 换掉

`overlay.yml` 通过 `dsh --profile skilleval --patch <file>` 叠加：

```yaml
- id: headless-runner
  disabled: true
- id: headless-startup
  disabled: true
- insert:                      # 新条目必须放在 insert 列表里
    - id: skill-eval-runner
      name: 'file:///D:/Games/robot/skill-eval/plugin/index.mjs'
      config:
        case: !!js process.env.DSH_EVAL_CASE
        workspace: !!js process.env.DSH_EVAL_WORKSPACE
        out: !!js process.env.DSH_EVAL_OUT
        user_questions: !!js process.env.DSH_EVAL_UQ
```

**坑**：写成 `- id: 新名字`（不加 insert）会被当成"按 id 改已存在条目"，报 `patch: entry "…" not found`，而且**这个错误不阻止启动**——一次性 runner 已经被关掉，没人负责退出，进程会安静挂死。

### 3.2 多轮怎么驱动

DSH 的 `Agent` 接口本来就提供了原语：

```js
agent.followup(userMessage)   // 追加到下一轮队列并唤醒驱动
await agent.whenIdle()        // 等到整个 agent 空闲
```

官方的 `runFixtureTurn()` 就是"造一条 user message → followup → 收事件 → 等 idle"四步。**多轮 = 把这四步放进一个 for 循环**，不需要改 DSH 本体。

### 3.3 提问链路怎么补回来

在 headless 里补上 `dsh-tool-ask-user` 工具，并注册一个脚本化的 `userQuestions` provider：

- `user_questions: "scripted"`：模型调用工具 → provider **立刻**按槽位返回答案 → 验证"提问→收到答案→继续"这条链路；
- `user_questions: "unavailable"`：provider 抛错（模拟"没人在"）→ 模型应退化为文字提问并停下 → 由下一轮的脚本用户消息给出答案，这才是真正的多轮。

### 3.4 判据只有一份

`plugin/assertions.mjs` 同时被在线 runner 和 `oracle.mjs` 使用，保证"自检通过的判据"与"实跑判分的判据"是同一段代码。

### 3.5 退出必须兜底

`appExit(code)` 之后还挂了一个 3 秒的 `process.exit(code)`。没有它，某些句柄会让事件循环活着，批跑会挂住。

---

## 4. 评测是怎么"作用到 skill 上"的

### 4.1 skill 在 DSH 里的生效链路

```
fixtures/<case>/workspace/.dsh/skills/<name>/SKILL.md
   ↓  dsh-skill-filesystem 扫描 cwd（项目根）下的 .dsh/skills
   ↓  会话开始注入 catalog：<available_skills> 里只有 name + description
   ↓  模型判断是否使用 → 调用 skill 工具（arguments 里带 name）
   ↓  返回 <skill_content name="…"> + <skill_instructions> 正文
   ↓  模型按正文行事
```

三个**可观测证据点**：catalog 注入（`user/message`）、`tool/call name=skill` 与参数、`tool/result` 里的 `<skill_content name="X">`。

### 4.2 两条世界线

| 臂 | 工作区 | 其它条件 |
|---|---|---|
| `with_skill` | 保留 `.dsh/skills/**` | 同模型、同脚本用户、同夹具、同断言、同轮数上限 |
| `without_skill` | 同一份夹具复制后**删掉 `.dsh/`** | 同上 |

差异只能归因于 skill —— 这就是 `lift` 的定义。

### 4.3 断言落在哪里（不落模型自述）

- **世界状态**：`plan.md` 是否存在、内容是否包含指定答案（`must_write_file` + `must_contain`）；
- **工具轨迹**：本轮是否调用过 `skill`、是否"先问再动手"（`must_ask_user` / `forbid_tools`）、是否重复追问（`must_not_ask`）。

### 4.4 两个杠杆，测的是不同东西

DSH 的 catalog **只有 name + description**（`whenToUse` 不进目录）：

- 改 **description** → 影响"skill 会不会被加载" → 看 `skillInvocations` 与 `turns[].tools`；
- 改 **正文** → 影响"加载之后做什么" → 看断言与世界状态。

**把路由提示写进 `whenToUse` 等于没写。**

### 4.5 边界

评测对象是**夹具工作区里的那份 skill**，不是你生产仓库里的 skill。要评真 skill：把它复制进夹具，或用 `--patch` 把 `skill-filesystem` 指到你的仓库：

```yaml
- id: skill-filesystem
  config: { includeDefaultRoots: false, watch: false, customSkillDirs: ["D:/path/to/your/skills"] }
```

`includeDefaultRoots: false` 很关键，否则 `~/.dsh/skills`、bundled skill 会漏进来污染对照。

---

## 5. 结果长什么样

### 5.1 单次报告 `out/<case>.<arm>.run<k>.json`

| 字段 | 含义 |
|---|---|
| `case` / `workspace` / `sessionId` | 用例、本次独立工作区、DSH 会话 id（可回查完整转录） |
| `model` | provider / model（保证两臂可比） |
| `wallMs` | 本次墙钟耗时 |
| `turnsUsed` / `maxTurns` | 实际用了多少轮 / 上限 |
| `userQuestionsAnswered` | 脚本化"人"回答过哪些提问（槽位、答案） |
| `totals` | inputTokens / outputTokens / cacheReadTokens |
| `passed` / `failedAssertions` | 总判定与失败断言清单（带证据） |
| `turns[]` | 逐轮：`turn` / `asked` / `tools[]` / `toolCalls[{name,arguments}]` / `assistantText` / `reason{kind}` / `usage` / `timedOut` / `assertions[{id,passed,detail}]` |

真实片段（同一用例的两个臂）：

```jsonc
// with_skill
{ "passed": true, "turnsUsed": 2, "wallMs": 6573,
  "totals": { "inputTokens": 9509, "outputTokens": 614, "cacheReadTokens": 35200 },
  "turns": [
    { "turn": 1, "tools": ["skill","ask_user_question"], "asked": true,
      "assertions": ["must_ask_user=PASS", "forbid_tools=PASS"] },
    { "turn": 2, "tools": ["write"], "asked": false,
      "assertions": ["must_write_file=PASS", "must_not_ask=PASS"] } ] }

// without_skill
{ "passed": false, "wallMs": 19830,
  "failedAssertions": ["forbid_tools","must_write_file","must_not_ask"],
  "turns": [
    { "turn": 1, "tools": ["pwsh","glob","pwsh","ask_user_question"],
      "assertions": ["must_ask_user=PASS", "forbid_tools=FAIL(used pwsh,pwsh)"] },
    { "turn": 2, "tools": [],
      "assertions": ["must_write_file=FAIL(file absent)", "must_not_ask=FAIL(asked again)"] } ] }
```

> **产物格式（CC15 起）**：每次运行额外写 `out/grading/<case>.<arm>.<run>.grading.json`（Anthropic skill-creator 兼容的 `expectations[{text,passed,evidence}]` + `summary`），聚合额外写 `out/benchmark.json`（`run_summary.{with_skill,without_skill,delta}`）。
> 两个引擎（DSH 与 Claude Code）由同一个模块 `shared/anthropic-artifacts.mjs` 生成，形状一致、可直接喂给 skill-up 之类的生态工具。**canary 用例不计入 `run_summary`**（它按设计必须失败）。

### 5.2 聚合报告 `out/summary.json` + 控制台表格

```
canary-never      with_skill  0/3  rate=0  wilson=[0,0.562]   canary=ok
clarify-multiturn with_skill  3/3  rate=1  ci95=[1,1]  wilson=[0.438,1]  wall= 7.7s  tokens=10,234
                  without     0/3  rate=0  wilson=[0,0.562]               wall=28.8s  tokens=14,222   lift=1
clarify-scripted  with_skill  3/3  rate=1  ci95=[1,1]  wilson=[0.438,1]  wall=10.5s  tokens=10,935
                  without     0/3  rate=0  wilson=[0,0.562]               wall=74.0s  tokens=24,070   lift=1
macro lift: 1 | canary: ok | 15 次运行合计 204,191 token
```

| 指标 | 定义 |
|---|---|
| `resolutionRate` | 该臂通过次数 / 运行次数 |
| `pass@k` | 该臂是否至少有一次通过 |
| `ci95` | Wald 95% 区间（与 skilljack 同口径）。**n=3 且 3/3 时会退化成 [1,1]，不可当真** |
| `ci95Wilson` | Wilson 区间，极端值下仍然诚实（3/3 → [0.438,1]） |
| `lift` | with 臂通过率 − without 臂通过率（单用例） |
| `macroLift` | 各用例 lift 的宏平均（用例等权） |
| `canary` | `ok` = 必挂的断言确实挂了；`BROKEN` = 判分器坏了，整轮数字作废 |

### 5.3 退出码

全部断言通过 → `0`；有失败 → `1`（可直接进 CI）。

---

## 6. 改了 skill 再跑，会得到什么

> 当前版本给的是**"与无 skill 基线"的对比**，不是"与上一版的自动对比"。做回归要把改动前后各跑一次（git stash 或复制旧版当第二个夹具），再比两份报告。

| 你看到的现象 | 含义 | 该怎么办 |
|---|---|---|
| with 臂 3/3 → 2/3，或某条断言 PASS → FAIL（带证据） | **真回归**，且定位到轮次与断言 | 直接看 `turns[].assertions` 落在第几轮，对照你改的那段正文 |
| `skillInvocations` 下降，甚至 `tools` 里不再出现 `skill` | **路由坏了**，多半动了 description | 检查 description；catalog 只截 500 字符，`whenToUse` 不参与路由 |
| 通过率不变，但 wall/tokens 明显变差 | skill 变啰嗦，让模型多绕路 | 读 `assistantText` 与 `tools`，砍掉没在挣钱的步骤 |
| `lift = 0`（两臂都过） | **这个用例测不出 skill 的价值**，不是"skill 没用" | 换/加强断言（夹具污染就会造成这种假象，现在会被卫生检查挡住） |
| `canary: BROKEN` | 判分器坏了 | 整轮作废，先修判分器 |

**改完 skill 的最小回归流程（便宜版）**：

```powershell
node oracle.mjs                                        # 判据自检，0 token
node run.mjs clarify-multiturn --arms with_skill --repeats 3
node report.mjs
```

成本量级：单用例单臂 3 次 ≈ 20–40 秒 / 3 万 token；全量（3 用例 × 2 臂 × 3 次）≈ 20 分钟 / 20 万 token。
**日常改 skill 用便宜版；只有发版或改 description 才跑全量。**

---

## 7. 防自欺三道闸

1. **oracle gate（跑批前，0 token）**：正向控制——把用例声明的期望产物合成出来，文件断言必须能过（证明判据可达，不是永远为假）；负向控制——canary 的断言必须挂。
2. **canary 用例**：挂一条永远不可能满足的断言。它若"通过"，说明判分器会放过任何东西，`report.mjs` 标 `BROKEN`，数字不可信。
3. **夹具卫生检查**：用例声明 `artifacts`，跑前若夹具里已存在这些文件就直接报错退出。**第一次跑时正是缺了这条，夹具里残留的 `plan.md` 让两臂都假 PASS、lift=0**，差点把"skill 没用"当成结论。

---

## 8. 能不能搬到 Claude Code / opencode / codex 上用

### 8.1 结论

**能，但要分层看：方法论与判据几乎 100% 可移植；运行器（runner）必须按 agent 重写。**

| 层 | 内容 | 可移植性 |
|---|---|---|
| 用例与判据 | `cases/*.json`（turns / slots / limits / assertions / artifacts / oracle）、`plugin/assertions.mjs` | **完全可移植**，与 agent 无关 |
| 实验设计 | 两臂（有/无 skill）= 文件系统差异、重复 N 次、oracle gate、canary、夹具卫生 | **完全可移植** |
| 统计与报告 | `report.mjs`（rate / pass@k / Wald+Wilson / lift / macroLift / token / 时长） | **完全可移植**（纯 Node，无 DSH 依赖） |
| 运行器 | `plugin/index.mjs`（DSH 插件：`agents.create` / `followup` / `whenIdle` / `session/event`） | **不可移植，必须重写** |
| A/B 开关 | DSH 用 `--patch` 改 `skill-filesystem`；其它 agent 靠"删掉/保留 skill 目录" | 概念可移植，做法不同 |
| 证据提取 | DSH 读会话事件流；Claude Code 读 SDK 元数据或 `~/.claude/projects/*.jsonl`；opencode 读 `run --format json` 事件 | **最需要适配的一层** |

### 8.2 推荐的移植做法：抽一个 `TranscriptAdapter`

把 runner 缩到一个很窄的接口——**只负责"跑一段多轮对话，吐出规范化事件"**：

```ts
interface TurnSpec { user: string; assert?: AssertSpec }

interface NormalizedTurn {
  turn: number
  tools: string[]                                  // 本轮的每个工具调用名
  toolCalls: { name: string; arguments?: string }[]
  assistantText: string
  usage?: { inputTokens: number; outputTokens: number; cacheReadTokens?: number }
  reason?: { kind: string }                        // completed / error / truncated…
}

interface Runner {
  run(caseFile, workspace, env): Promise<{ turns: NormalizedTurn[]; wallMs: number; raw: unknown }>
}
```

断言引擎、oracle gate、统计、报告都只吃 `NormalizedTurn[]`。换 agent = 换一个 adapter，其余不动。

### 8.3 Claude Code（本机已装 2.1.170）

- **skill 位置**：`.claude/skills/<name>/SKILL.md`（本机 `D:\work\skill-test-kit` 已验证）。
- **多轮怎么做**：不用写插件。`claude -p "<第一轮>" --output-format json` 拿到 `session_id`，再用 `claude -p "<第二轮>" --resume <session_id>` 续跑；或直接用 `@anthropic-ai/claude-agent-sdk` 的流式输入模式（本机 `skill-test-kit` 已装该 SDK + promptfoo，可直接复用）。
- **提问链路**：Claude Code 没有 `ask_user_question` 工具，模型只会用文字提问——**正好对应我们 `user_questions: "unavailable"` 那一种模式**，脚本答案放到下一轮用户消息里即可，判据不用改。
- **证据提取**：SDK 会给 `metadata.skillCalls`（skill-test-kit 就是这么判的）；CLI 路线则解析 `--output-format stream-json` 的事件，或直接读 `~/.claude/projects/**/*.jsonl`（本机已有 157 个转录文件）。判定"`Skill` 工具被调用 + 参数里的 skill 名"即可。
- **现成先例**：`D:\work\skill-test-kit` 已经是跑通的 Claude Code 版 L0+L1（3 skill×15 探针 14/15、6 skill×26 探针 23/26），可以直接把它当 `claude-code adapter` 的实现参考，把我们的用例 schema 与统计口径接上去。

### 8.4 opencode（本机未安装）

- **skill 位置**：`.opencode/skills`（skilljack 的挂载约定）。
- **运行与取证据**：`opencode run --format json --auto`，解析其 JSON 事件流；skill 调用判定看 `skill`/`activate_skill` 工具，或退化为"读到了 SKILL.md"。
- **多轮**：opencode 的 `run` 是否支持续跑会话需要实测；若不支持，就退回**单轮化的 A 档**（把历史贴进夹具/提示词），或换成"一次输入里预置多轮历史"。

### 8.5 codex（本机未安装，但 SDK 已在 skill-test-kit 里）

`codex exec --json --skip-git-repo-check --ignore-user-config --ephemeral`；**注意 codex 没有 skill 工具**，它的"加载 skill"表现为 **shell 读 SKILL.md**，所以"是否生效"的判据形态与 DSH/Claude Code 不同——这正是跨 agent 不可直接比数字的原因，报告里必须带上 harness 元数据。

### 8.6 更省事的一条路：直接用 skilljack-evals

`olaservo/skilljack-evals` 就是一个**多 runner 的 skill 评测 CLI**（claude-code / claude-sdk / codex / gemini / opencode），自带 oracle gate、deterministic reward、judge、缓存、并发、GitHub Action，指标口径（resolution rate / pass@k / skill lift / invocation rate / 95% CI）与本文一致。

所以现实选择是二选一：

- **要快**：把我们的用例与断言设计搬进 skilljack 的 `evals/<task>/task.md` + `verifier/verify.mjs` 格式，直接用它跑 Claude Code/opencode/codex；
- **要掌控**：保留我们这套（DSH 上是原生实现），按 §8.2 给 Claude Code/opencode 各写一个 adapter。

---

## 9. 已知限制与路线图

**限制**

1. 无"自动版本对比"（`v0 / v1 / without` 三臂、won/lost/tie）——回归要人工跑两次；
2. 批量是**串行**的，且未做每 case 独立 `DSH_HOME`（并发前必须先解决 profile 目录共享）；
3. 断言只有文件级（存在性 + 子串），没有数值/公式/阈值类结构化断言；
4. 失败没有按模式切片（`discovery_failure / false_positive / instruction_ambiguity / missing_guidance / agent_error`）；
5. 没有 LLM 用户模拟器（开放协商类用例只能靠脚本轮次或人工）；
6. `ci95` 用 Wald，n 小时不可靠（已并报 Wilson，但更严谨应上 bootstrap 或增加重复次数）。

**路线图（优先级）**

1. 版本对比三臂 + `won/lost/tie`（对应官方 `history.json` 口径）;
2. 并发 + 每 case 独立 `DSH_HOME`；
3. 结构化产物断言（数值/公式/阈值）；
4. 失败模式切片 + 与人工 gold 的一致率校准；
5. `TranscriptAdapter` 抽象 + Claude Code adapter（复用本机 skill-test-kit 经验）。

---

## 10. 附录

### 10.1 文件清单

| 文件 | 作用 |
|---|---|
| `oracle.mjs` | 判据自检（正向 + 负向控制），0 token |
| `run.mjs` | 批量跑：用例 × 臂 × 重复次数；夹具卫生检查；工作区隔离 |
| `report.mjs` | 聚合历史 run → summary.json + 控制台表格 |
| `plugin/index.mjs` | 多轮 runner 插件（DSH） |
| `plugin/assertions.mjs` | 产物断言（runner 与 oracle 共用） |
| `overlay.yml` | `--patch` 叠加：换掉一次性 runner |
| `cases/*.json` | 用例；`cases/INDEX.txt` 是跑批清单 |
| `fixtures/<case>/workspace/` | 夹具工作区（`.dsh/skills/<skill>/`） |
| `out/` | 单次报告、聚合报告、临时工作区 |

### 10.2 命令速查

```powershell
$NODE = 'D:\Users\Administrator\AppData\Local\nvm\v24.19.0\node.exe'

& $NODE oracle.mjs                                  # 判据自检
& $NODE run.mjs --repeats 3                         # 全量 A/B（读 cases/INDEX.txt）
& $NODE run.mjs clarify-multiturn --arms with_skill --repeats 3   # 便宜版
& $NODE report.mjs                                  # 出报告
& $NODE run.mjs canary-never --arms with_skill      # 只跑判分器自检用例
```

### 10.3 踩过的坑

1. **headless 没有多轮、也没有 `ask_user_question`** —— 必须自己搭（本文档存在的理由）。
2. **overlay 新条目必须放 `insert:`**，否则报 `entry not found` 且**不阻止启动**，进程安静挂死。
3. **插件跑完必须兜底退出**（`appExit` + 3 秒 `process.exit`）。
4. **夹具污染会让两臂都假 PASS**（残留产物满足断言）→ 现在有 `artifacts` 卫生检查。
5. **Wald CI 在 3/3 时退化成 [1,1]** → 并报 Wilson。
6. **Windows 控制台看中文是乱码，但报告 JSON/产物文件是 UTF-8**（正确）；`dsh` 不在 PATH，`D:\nvm4w\nodejs` 当前指向没有 dsh 的 v22，必须用 v24 绝对路径。
7. **`run.mjs` 的参数解析**：裸 token 若不是某个 `--flag` 的值就当成 case id（曾经把 `--repeats 3` 的 `3` 当成了用例名）。


---

## 11. 这套评测借用了哪些已有能力（来源清单）

原则：**只借口径、设计与流程，代码全部重写**。下面逐条对应到本仓库的具体文件。

### 11.1 借用自公开项目（方法论与指标口径）

| 来源 | 借了什么 | 落在本仓库哪里 |
|---|---|---|
| **[anthropics/skills · skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)** | 两臂实验法（`with_skill` / `without_skill` **同批次**跑，不许先跑完一组再补）；基线选择（新 skill = 无 skill；改 skill = **改之前的快照**）；"断言必须可验证、能用脚本就别肉眼判"；"两臂都过 = 断言无区分度，要换掉"；迭代目录与 `timing.json` 必须当场落盘；反模式（禁止 ALL CAPS 的 ALWAYS/NEVER、禁止为测试集过拟合、3 个用例都在重造同一个 helper 就该固化成脚本） | `run.mjs`（两臂 + 工作区隔离）、`report.mjs`（解读口径）、本说明书 §6 的五类信号 |
| **[olaservo/skilljack-evals](https://github.com/olaservo/skilljack-evals)** | **指标定义照抄**：`resolutionRate` / `pass@K` / `binomialCI`(95% Wald) / `skillLift` / `macroSkillLift` / `skillInvocationRate`（且**反触发任务必须剔除出分母**）；oracle gate 思路（先用参考解证明"任务可解 + verifier 没坏"）；"deterministic reward 是唯一权威，judge 只做诊断"；多 runner 适配器思想（claude-code/codex/gemini/opencode） | `report.mjs` 的 `stats()`、`oracle.mjs`、§8.2 的 adapter 设计 |
| **[benchflow-ai/skillsbench](https://github.com/benchflow-ai/skillsbench)** | **"Oracle must pass before agent runs"**；测试设计规范（<10 条除非有理由、parametrize 不复制、exists+valid+correct 合成一条）；阈值要取"作者保存的 artifact"而不是照抄指令；反作弊（不许 grep 源码关键字式假测试）；轨迹审计要读事件流而不是聊天记录；**跨 harness 数字不可直接比** | `oracle.mjs`、`cases/*.json` 的 `oracle` 字段、本说明书 §8 |
| **[crashcartlabs/skill-testing](https://github.com/crashcartlabs/skill-testing)** | 静态检查清单（frontmatter 合法性、`name` 必须等于目录名、description ≤1024 字符/第三人称/≥2 个具体触发条件、密钥与危险命令扫描、`tests.md` ≥3 场景 + `Last verified` 90 天过期）；"description 要 pushy 且 sharp" | 调研报告 §9.11 的 L0 清单（**尚未实现进代码**） |
| **[rhyanvargas/agentic-development-starter-kit](https://github.com/rhyanvargas/agentic-development-starter-kit)** | **grader canary**（一条固定必挂的断言；判它 PASS 就作废整轮数字）；**fails-closed 聚合**（有 PENDING 或 canary 未判 FAIL 就不写结果、非零退出）；作者 ≠ 评分者；盲评是语义断言的前提；CI 分层（形态校验可硬门禁，通过率门禁等 flakiness/成本基线摸清再上） | `cases/canary-never.json` + `report.mjs` 的 `canary: BROKEN`、`oracle.mjs` 的负向控制 |
| **[addyosmani/agent-skills · evals](https://github.com/addyosmani/agent-skills/tree/main/evals)** | 三层评测（结构 / 触发路由 / 行为）；case 文件 schema（`trigger.positive` / `trigger.negative` 带 `owner`）；下限门槛（≥3 正 + ≥2 负）；**触发门用 rank-1 率**；描述碰撞检测（两两相似 ≥75% = error） | 调研报告 §9.11；`cases/*.json` 的字段划分 |
| **[tony-adamson/groundwork-bench](https://github.com/tony-adamson/groundwork-bench)** | deterministic 与 judge 的权重分配（0.7 / 0.3，judge 挂了退化）；judge 输出的确定性解析（括号深度取第一个平衡 JSON、clamp、归一化）；避免自评（判分模型与被测模型不同源） | 调研报告 §9.14（尚未实现 judge 层） |
| **[ericrisco/rsc-harness](https://github.com/ericrisco/rsc-harness)** | 五段管线 dataset→runner→scorers→metrics→gate；judge 校准（模型能力 ≥ 被测、先写理由再给分、pairwise 优于 pointwise、**交换 A/B 位置**、先报与人类 gold 的一致率）；回归门对 committed baseline + bootstrap CI；反模式 8 条 | 调研报告 §9.14（路线图第 4 项） |
| **[HeshamFS/materials-simulation-skills](https://github.com/HeshamFS/materials-simulation-skills)** | "**价值 = with/without 的 delta，不是绝对通过率**"；能机检的一律改成 script check；结果四象限读法（都过=无信号 / 都挂=修或删 / 只有 with 过=价值点 / 高方差=用例或指令含糊） | 本说明书 §6 的信号表 |

### 11.2 借用自本机已有资产（不是网上）

| 来源 | 借了什么 |
|---|---|
| **`D:\work\skill-test-kit`**（本机已跑通的 Claude Code 版评测包） | 探针 schema（`positive` / `negative` / 跨边界 `expect: null`）；修复环（只复测"原失败 + 回归"子集）；失败分类的读法；**14 条实测坑**（探针必须自包含、轮数上限是头号噪声源、必须 bust cache、混淆 ≠ bug、执行型 skill 会丢证据）；成本模型 |
| **DSH 本体** | 多轮驱动原语 `agent.followup()` + `await agent.whenIdle()`；带轮号的会话事件流（`turn/start`、`tool/call.data.turn`、`step/end`、`assistant/message.usage`）；`ctx.on('session/event')`；`--patch` overlay + profile 组合；`dsh-tool-ask-user` 与 `ctx.userQuestions` 接缝；`dsh-skill-filesystem` 的 catalog 注入；`appExit`；`--dump-config`；会话 JSONL 持久化 |
| **DSH 源码仓的测试基建**（读懂了但未直接引用） | `examples/headless-agent/tests/` 的"真 boot + 事件流断言"范式、`loader-smoke`、`llm-replay`（零 token 确定性回放），`docs/testing.md` 的"验证世界而不是模型自述" |

### 11.3 借用自线上服务

| 服务 | 用途 | 备注 |
|---|---|---|
| `api.github.com`（GitHub REST API） | 抓取 38 份最佳实践原文与仓库文件树 | `raw.githubusercontent.com` 在本机不可达，GitHub API 可用；未认证限额 60 次/小时 |
| DeepSeek 官方模型 API | 真正跑 agent（`deepseek-official / deepseek-flash`） | 15 次运行约 20 万 token |
| npm registry（`registry.npmjs.org` / `registry.npmmirror.com`） | 探测可用性与包元数据 | 未用它安装依赖 |

**没借到的**：OpenAI 的 `developers.openai.com/blog/eval-skills`（返回 403）、HuggingFace / arXiv 论文正文（超时）——所以 SkillsBench 的**论文数字**没有被采信，只用了它仓库里的工程规范。

### 11.4 哪些是本项目原创的

1. **在 DSH 上用插件替换 `headless-runner` 来实现多轮**（原语是 DSH 的，"换掉一次性 runner 并自己驱动"这个做法是本项目搭的）；
2. **槽位化答案银行**：按**关键词匹配模型实际问的问题**来应答，而不是按轮次索引——这样模型多问一轮也不会答错位（抗轮次漂移）；
3. **`user_questions: scripted | unavailable` 两种模式**：前者验证"提问→拿到答案→继续"，后者验证"没人应答时退化为文字提问 + 多轮脚本用户"；后者恰好就是 Claude Code 的现实形态（它没有提问工具）；
4. **夹具卫生检查**（用例声明 `artifacts`，跑前若已存在就报错退出）——由我自己踩的"夹具污染导致两臂假 PASS"事故倒逼出来；
5. **并报 Wilson 区间**：Wald 是照抄 skilljack 的，但 3/3 时退化成 [1,1] 这个问题是我在跑出真实数据后发现的；
6. **oracle gate 的 0 token 实现**：思路来自 SkillsBench/skilljack，但"用合成产物对**同一份断言代码**做正向控制"这个轻量做法是本项目的。

### 11.5 一句提醒

这些仓库都带 `LICENSE`，我**没有逐一核对**许可条款。口径、公式、流程属于方法论，代码是重写的；但如果要把用例 schema 或报告格式直接搬进对外发布的产品，建议先核对相应 LICENSE。

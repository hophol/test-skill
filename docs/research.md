# Agent Skill 评测调研报告

调研时间：本次会话（本机 DSH 环境实测）
调研对象：如何在 DSH（DeepSeek Harness）体系下对 agent skill 做可复现、可回归、成本可控的自动化评测
方法：① 通读本机已有的 skill 测试工具包 `D:\work\skill-test-kit`（为 Claude Code 实测通过）② 阅读 DSH 源码/文档中的 skill 机制 ③ **在本机实跑 DSH headless 回路验证可行性**（正例 + 负例 + 转录解析全部实测通过）④ 外部生态检索（受网络限制，仅得来源清单）

---

## 0. 结论摘要（TL;DR）

1. **评测要分三层，不要混在一起**：L0 结构门禁（免费、确定）→ L1 路由/触发（模型级、概率性）→ L2 任务级效果与"相对无 skill 的增量（lift）"。L0 拦错、L1 拦"该触发不触发/不该触发乱触发"、L2 才回答"这个 skill 到底有没有用"。
2. **本机已有一套跑通的 L0+L1 实现**（`skill-test-kit`，promptfoo + claude-agent-sdk），它的**探针资产、指标口径、坑清单可直接迁移**，但运行器/断言/注册表三块必须重写。
3. **DSH 有一条原生、比 Claude Code 更适合做评测的回路**（本次已实测）：
   `dsh --profile headless "<探针文本>"` → 落盘会话转录 `~/.dsh/sessions/--<cwd slug>--/session-<uuid>/session.jsonl.zstd` → 从转录里**确定性地**读出"是否调用了 skill、调用了哪个、轮数、token、耗时、终态"。
   这意味着工具包坑 #13（执行型 skill 报错后证据丢失）在 DSH 上**天然被解决**：证据在盘上，不在 SDK 返回值里。
4. **最小可行评测 = 一个 fixture 工作区 + 一次 headless 运行 + 一次转录断言**。本次实测单次成本约 8.3k 输入 token、2 次模型请求、数秒墙钟；负例（不该触发）同样可判定。
5. 建议落地顺序：M0 转录解析 + 断言库（1 天）→ M1 批量跑 + 路由矩阵报告（复用 skill-test-kit 探针）→ M2 任务级 lift 与 CI 回归。
6. **DSH 源码仓自带可复用基建**，不必从零造：`packages/test-support/loader-smoke`（隔离 `DSH_HOME`/`cwd` 的进程级真 boot + 事件流 harness）、`packages/test-support/llm-replay`（把一次真实会话转成**零 token 确定性回放**做回归）、`examples/headless-agent/tests/`（swebench 式行为 e2e 范式）、`docs/testing.md`（“验证世界，而不是模型自述”）。缺口只有一个：**没有批量跑 + 打分 + 报告**这一层。
7. **中断路径的证据也保得住**（实测）：把跑着的 headless 进程杀掉，会话文件里仍有 30 条事件，含 skill 目录注入与已发出的 `tool/call`。

---

## 1. 本机已有资产：`D:\work\skill-test-kit`（直接可借鉴）

### 1.1 架构与数据流

```
skills-sample/.claude/skills/**  （被测 skill = SKILL.md + 各自 probes.yaml）
probes/cross-boundary.yaml      （平台维护的跨边界模糊请求池）
scripts/build_registry.py       → skills.json（单一事实来源）
scripts/lint_skill.py           → L0 结构门禁（免费、exit code 即结论）
scripts/probes_to_promptfoo.py  → promptfooconfig.generated.yaml
promptfoo eval                  → results/*.json
scripts/report.py               → 路由矩阵（混淆矩阵 + 分组触发率 + 失败明细）
```

- 修复环：改 description → **只复测受影响子集**（`fix-check.yaml` = 原失败 + 回归）→ 复测。
- `versions.lock` 固化版本与成本快照；`PITFALLS.md` 14 条实测坑。

### 1.2 L0 检查项（确定性，零成本）

错误级：缺 SKILL.md；缺 frontmatter 分隔；frontmatter 不完整或 YAML 解析失败；出现白名单（name/description/license/compatibility/allowed-tools/metadata）之外的字段；缺 name/description；**目录名 ≠ name**；description < 10 字或 > 1024 字。
警告级：SKILL.md > 500 行；缺 probes.yaml；正向探针 < 3 条。

### 1.3 L1 探针 schema 与判据（零裁判模型）

```yaml
# 每个 skill 自己的 probes.yaml
positive:            # ≥3 条，真实措辞、多说法，防背题
  - "帮我..."
negative: []         # 可选
```
```yaml
# probes/cross-boundary.yaml（平台级边界池）
- text: "..."        # 探针必须**自包含**（不引用上下文）
  expect: skill-name # 字符串 = 应触发该 skill；null = 负例，任何 skill 都不得触发
  note: "交界成因 + 定性结论（真混淆 / 合法链式入口）"
```
断言只有两类：`skill-used=<name>`（读运行器返回的 `metadata.skillCalls`）与负例的单表达式 JS 断言 `((context.providerResponse?.metadata?.skillCalls) || []).length === 0`。

### 1.4 实测结论（2026-09-01）

| 项 | 结果 |
|---|---|
| L0 | 埋错 skill（非法字段 / 目录名不一致 / 描述过短）全部抓到 |
| L1 基线 | 3 skill × 15 探针 = 14/15（唯一缺口是"链式入口"定性分歧） |
| L1 扩池 | 6 skill（含 3 个外部）× 26 探针 = 23/26；负向 4/4；外部 skill 与存量零串扰 |
| flaky 实证 | 同一批 15 条重跑 12/15（2 条被 max_turns 掐断、1 条边界未触发）→ **单次结果不可信，必须重复跑** |
| 成本 | 3×15 ≈ 30 万 token / 2.5 min；6×26 ≈ 89.5 万 token / 12 min（并发 4）；外推 100 skill×20 探针 ≈ 7000 万 token |

### 1.5 必须迁移的坑（精选，完整 14 条见 `D:\work\skill-test-kit\PITFALLS.md`）

- **探针必须自包含**：引用上下文的探针在空工作区会退化成"反问澄清"，系统性低估触发率（含糊探针还会双峰 flaky）。
- **轮数上限是评测的头号噪声源**：max_turns=3 时 15 条挂 5 条；执行型 skill 需 ≥20 轮（单探针时间 ×3）。
- **缓存必须关**：不 bustCache 命中率虚高；负例必须在"全部 skill 可见"下跑。
- **混淆 ≠ bug**：稳定进入上游 skill 是 SKILL.md 自己规定的合法链式入口，混淆对必须人审定性（改 description 还是改期望值）。
- **报告不要排名**：只显示与自身基线的 Δ；通过率不进绩效；失败带证据路由给 owner。

---

## 2. DSH 侧的 skill 机制（评测面在哪）

### 2.1 生命周期

`ctx.skills`（`@deepseek-ai/dsh-skill`）= 纯 provider 注册表；`dsh-skill-filesystem` 提供本地文件源；`dsh-tool-skill` 负责**模型侧目录注入 + `skill` 工具**。

- 发现根（rank 越小越优先）：`<projectRoot>/.dsh/skills`(100) → `<projectRoot>/.agents/skills`(200) → `customSkillDirs`(300) → `~/.dsh/skills`(400) → `~/.agents/skills`(500) → bundled(600)。projectRoot = 最近的含 `.git` 的祖先，否则 cwd。
- 形态：目录包 `<name>/SKILL.md` 或扁平 `<name>.md`；**不递归**发现嵌套 `**/SKILL.md`。
- frontmatter：必需 `name`（文法 `^[a-z0-9]+(?:-[a-z0-9]+)*$`）、`description`（非空）；可选 `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable`（布尔，默认都是 true）。
- **两个“静默失败”点，L0 必须专门拦**：① 旧键名（`disableModelInvocation`/`modelInvocable`/`userInvocable`）会直接抛错；② 其余 frontmatter 解析失败只 `logger.warn` 然后**跳过该 skill**——目录不报错、模型侧也不报错，这个 skill 就此消失。
- 同名冲突：rank 决定胜出，且全层按 scope 分层（host / preset）。
- 变更检测：Chokidar 监听 + 第一方 write/edit 同步失效（热更，评测时可即时换 skill）。

### 2.2 模型看到什么（评测的关键：描述即路由）

会话开始时，若存在 model-invocable skill 且 `skill` 工具可见，注入一条 **durable user-role `<system-reminder>`**：

```markdown
<system-reminder>
A skill is a reusable set of task-specific instructions. The following skills are available in this session:
<available_skills>
- `<name>`: <description，默认截断 500 字符>
</available_skills>
...
```

**目录里只有 name + description**（`whenToUse` 不进目录）→ 因此 **description 是唯一的路由杠杆**，L1 评测本质是在评测 description（与 Claude Code 同一结论）。
加载是**显式**的：模型必须调用 `skill` 工具（`name` 精确匹配），结果渲染为 `<skill_content name="...">` + `<skill_resources>` + `<skill_instructions>`。
用户显式调用（斜杠/手势）走另一条路：把同一份 `renderSkillContent` 内联注入，并打上 `skill-invocation` message source——**这是第二条可评测面**（用户显式调用路径不经过 `skill` 工具）。

### 2.3 可用的评测旋钮（profile patch）

`dsh --profile headless --dump-config` 实测得到的 entry id：

| entry id | 用途 |
|---|---|
| `skill-filesystem` | `customSkillDirs` + `includeDefaultRoots: false` → **隔离的 skill 夹具根**（评测必备：排除项目/user 存量干扰） |
| `tool-skill` | `catalogDescriptionMaxLength`（默认 500）→ 评测"描述长度 vs 路由准确率 vs 上下文成本" |
| `session-title-llm` | 每次 headless 运行都会多打一次标题生成请求（实测确实发生）→ 评测批量跑时建议 patch 关闭，省掉 ~1 次调用/run |
| `skill-badge` | web 侧展示，headless 已 disabled |

profile patch 文件：`~/.dsh/profiles/headless/cordis.patch.yml`（YAML 数组，id 定向覆盖）。`dsh --profile headless` 首次使用会自动初始化 profile（实测已自动生成，bundles = `dsh-base` + `dsh-headless`）。

源码侧补充（决定 harness 怎么写）：

- `--patch <file.yml>` 可重复，必须写在 `--profile` 之后；层序 = bundle 层 → profile patch → `$DSH_HOME/cordis.patch.yml` → `--patch` overlay。patch 是**整行 config 替换**（不是深合并），所以 A/B 只要两份小 YAML：

```yaml
# overlays/with-skill.yml
- id: skill-filesystem
  config: { includeDefaultRoots: false, watch: false, customSkillDirs: ["<候选 skill 目录>"] }
- id: agent-default-model
  config: { provider: deepseek-official, model: <固定模型> }
# overlays/without-skill.yml —— 同一行改成 customSkillDirs: []
```

- **没有 `--cwd`、没有 `--model`**：workspace 只能靠 `cd`（`process.cwd()` 同时决定 agent meta.cwd、fs sandbox、workspaceRoot）；模型只能靠 patch 或 `settings.yaml` 的 `agent-default-model` 段。→ 跑批必须**显式 cd 到夹具目录 + 显式 patch 模型**，否则基线不可比。
- 跑前用 `--dump-config`（可与 `--patch` 同用）验证组合差异，避免“以为改了其实没生效”。

---

## 3. 本次实测：DSH 原生评测回路（全部已跑通）

### 3.1 执行

本机 `dsh` **不在 PATH**，且 `D:\nvm4w\nodejs` 这个 symlink 当前指向 v22.16.0（该目录下没有 dsh）。实测可用的调用方式：

```powershell
& 'D:\Users\Administrator\AppData\Local\nvm\v24.19.0\node.exe' `
  'D:\Users\Administrator\AppData\Local\nvm\v24.19.0\node_modules\@deepseek-ai\dsh\lib\bin.js' `
  --profile headless "<探针文本>"
# 工作目录（workdir）= 夹具工作区；退出码 0 = 最后一个 turn/end 是 completed，否则 1
```

### 3.2 正例（skill 应被加载）

夹具：`D:\Games\robot\_evalscratch\.dsh\skills\ping-check\SKILL.md`（指令：只回一行 `PONG-SKILL-OK`）。
探针：`帮我做一次 ping 检查`

实测结果：stdout = `PONG-SKILL-OK`，exit 0；转录中依次出现：
1. `user/message` = 注入的 `<available_skills>` 目录，含 `- \`ping-check\`: ...`
2. `assistant/message` 里 `tool-call name="skill" arguments={"name": "ping-check"}`（usage: input 8053 / output 45）
3. `tool/result` = `<skill_content name="ping-check">…<skill_instructions>…`
4. `turn/end reason.kind = "completed"`

### 3.3 负例（不该触发）

同一夹具，探针：`用一句话解释一下什么是闭包`
实测：**没有任何 `skill` 工具调用**，模型 reasoning 明确写 "No skill needed"，exit 0。
→ 负例判据在 DSH 上可直接落地：`tool/call 且 name==='skill'` 计数为 0。

### 3.4 转录格式与解析（评测的判据来源）

- 路径：`~/.dsh/sessions/--<cwd 归一化 slug>--/session-<uuid>/session.jsonl.zstd`
- 文件是**追加式多帧 zstd**：首行 `{type:"session",...header}`，其后每个追加帧是一批事件。**实测 Node 的 `zlib.zstdDecompressSync(整文件)` 只解出第一帧**（168 字节），必须逐帧解码。
  正确做法（按优先级）：
  - **一方 API（首选）**：`ctx.sessionPersistence.load(id)` 返回 `{ meta, events }`，另有 `inspect(id)` / `readFrom(id, fromSeq)` / `list()` / `readRaw(id)`；或 `ctx.sessionQuery` 的 `listSessions / readSession / listEvents / readSurface / searchEvents / traceSession`。两者都会展开 packed chunk 行，调用方不必碰 zstd。
  - **纯文本场景**：`parseSessionLog(text)`（`@deepseek-ai/dsh-session`）。
  - **必须自己解压时**：`createZstdFrameDecoder()`（`dsh-session-persistence-jsonl`）+ 逐行 `decodeStorageRecord`——`assistant/chunk` 会被打包成 `text-chunks` / `reasoning-chunks` / `tool-call-chunks` 行，不能当普通事件直接读。
  - 兜底（本次实测可用）：扫描 zstd magic `28 B5 2F FD` 逐个偏移尝试解压并拼接；能拿到大部分判据字段，但会漏掉 packed chunk 的展开语义。

本次解码出的事件类型（一次 2 步的 run 共 40 条）：
`session, permission/preset, sandbox/mode, approval/policy, agent/inbox/spliced, turn/start, step/start, user/message, session/title, request/header, request/context, assistant/chunk, text-chunks, tool-call-chunks, assistant/message, tool/call, tool/result, step/end, reasoning-chunks, turn/end`

断言可直接取的字段：

| 断言目标 | 事件/字段 |
|---|---|
| 是否调用了 skill、哪个 | `tool/call.data.name === "skill"`，`JSON.parse(arguments).name` |
| skill 是否真的加载成功 | `tool/result` 文本含 `<skill_content name="X">` |
| 最终答案 | 最后一条 `assistant/message` 的 text 段 |
| 轮数/步数 | `step/end` 计数、`turn/end.data.turn` |
| token/成本 | `assistant/chunk(data.chunk.type==='usage')` 与 `assistant/message.data.usage`：`inputTokens/outputTokens/cacheReadTokens/reasoningTokens` |
| 模型/路由 | `request/header.data.header.config`（provider/model/reasoningEffort/maxTokens）、`request/context` |
| 终态 | `turn/end.data.reason.kind`（`completed` / 其它 = 失败或截断） |
| 耗时 | 事件 `time` 字段（毫秒）差分；另有 `dsh-session-stats` 投影给出 ttft/decode/toolMs |

补充：`dsh-session-stats` 提供 turn/step 计数与 LLM/tool/首 token/解码墙钟；web profile 还有 `GET /api/session.export?sessionId=<id>&includeDescendants=true` 可直接拉 ZIP（含原始 JSONL），适合做"人工抽检证据包"。

### 3.5 中断路径的证据留存（本次实测，重要）

故意跑一个 90 秒任务并在执行中杀掉进程，事后解码会话文件：**文件仍在，8 个帧 / 30 条事件**，包含注入的 `<available_skills>` 目录、`request/header`（模型与 effort）、以及已经发出的 `tool/call`；缺的只是 `tool/result` / `step/end` / `turn/end`。

→ **DSH 上“模型到底调没调 skill”这类证据不依赖进程正常结束**：被 kill / 报错 / 超时的 run 依然可判分。报告口径上把“缺 `turn/end` 或 `reason.kind` 不是 `completed`”归入**异常终态**，与“未触发”分开统计即可。这正是 skill-test-kit 坑 #13 想要的“正解”。

---

## 4. 外部生态现状（受限说明）

本机 **`raw.githubusercontent.com` 与 huggingface 不通**，`web_search` 只返回来源清单、无正文——**但 `api.github.com` 可用**，所以本章最初只能列标题；**其中 6 个仓库的 38 份原文已抓下来逐字读过，结论见 §9**（未抓到的：OpenAI 的 `developers.openai.com/blog/eval-skills` 返回 403、HuggingFace/arXiv 超时）。以下保留最初检索到的清单供查证：

- SkillsBench（benchmark：skill 在多样任务上的有效性 / agent 使用 skill 的能力）— `github.com/benchflow-ai/skillsbench`、论文页 `huggingface.co/papers/2602.12670`
- skilljack-evals（CLI：测 agent 对 Agent Skills 的 discoverability / instruction adherence / output quality）— `github.com/olaservo/skilljack-evals`
- Anthropic：`Improving skill-creator: Test, measure, and refine Agent Skills`（claude.com/blog）
- addyosmani/agent-skills 的 `evals/`、groundwork-bench（确定性评分 + LLM-as-judge）、claude-caliper 的 `skill-eval`、materials-simulation-skills 的 `skill-evaluator/methodology`、微软 copilot-for-azure 的 `sensei/references/SCORING.md`
- 生态共识（从命名与工具能力可推、且与本机工具包结论一致）：**三层 = 发现/触发（discoverability）、指令遵循（adherence）、产出质量（quality）**，判分尽量确定性优先、LLM 裁判兜底。

> 若要引用其中具体数字/方法，需在能联网的机器上抓正文复核（本机只能给出 URL）。

---

## 5. 评测设计（建议口径）

### 5.1 三层指标

| 层 | 测什么 | 判据 | 成本 |
|---|---|---|---|
| **L0 结构** | frontmatter 合法性、命名/目录一致、描述长度、文件规模、**同名冲突/遮蔽**（DSH 特有：多根 rank 覆盖） | 纯静态，exit code | 0 |
| **L1 路由** | 正例命中率、负例误触发率、混淆矩阵、**稳定率（重复 N 次）**、上下文成本（catalog 字符数） | 转录里 `skill` 调用是否存在及名称 | 低（每探针 1 次 run） |
| **L2 效果** | 任务成功率、**lift = P(成功\|有 skill) − P(成功\|无 skill)**、指令遵循度、token/轮数增量 | 产物断言（文件/测试/脚本）优先，rubric 裁判兜底 | 高（每条 2×N 次 run） |

### 5.2 判据优先级（硬规则）

1. **确定性判据优先**：退出码、`skill` 调用名、产物存在性、脚本自检（让 skill 自己产出可机检文件，见坑 #13 的对策 a）。
2. **LLM 裁判只用于"质量类"残余维度**，且必须给 rubric + 只输出结构化分数；裁判模型与被测模型不同族时结论更可信。
3. **重复取多数**：每条探针 runs=3（`取多数`），报告里同时给"稳定率"；单次结果不写入基线。
4. **A/B 必须同日同配置**：有 skill / 无 skill 两组用同一 fixture、同一模型、同一 `reasoningEffort`，只改 skill 可见性（推荐：`skill-filesystem.config.customSkillDirs: []` + `includeDefaultRoots: false` 得到"零 skill"对照，而不是删目录——后者仍可能被 user/bundled 根污染）。

### 5.3 探针设计规范（继承工具包 + DSH 适配）

- 自包含：把上下文贴进探针，或在 fixture 工作区预置文件。
- 正例 ≥3 条、措辞多样；负例覆盖"最容易被误吸的邻居话题"。
- 边界例（cross-boundary）单独成池，`expect` 可为某 skill 或 null，`note` 记定性。
- 执行型 skill 单独分层，给更高轮数上限与更长超时。
- **不要**用"看看这个需求"这类指代不明的探针。

### 5.4 成本模型

单 run 成本 ≈ 输入 tokens（system prompt + catalog + 探针 + 工具结果）× 次数。本次最小实测量级：**skill 正例 run ≈ 8.3k 输入 token / 2 请求**；同夹具负例 ≈ 8.1k（含缓存读取）。
L1 全量 ≈ `skill 数 × 探针数 × runs × 单 run tokens`；L2 再 ×2（A/B）。
按工具包实测（≈3.3 万 token/探针，含长会话）外推，规模化前必须：① 探针自包含 + 夹具预置，减少 agent 乱找文件；② 分层设置轮数上限；③ 关闭标题 LLM；④ 只有 L0 与受影响子集进 CI，L1/L2 按需跑。

---

## 6. DSH 评测 harness 实现方案（可落地）

### 6.0 可直接复用的仓库自带基建（别再自己造）

| 需求 | 现成实现 | 位置 |
|---|---|---|
| 真 boot 一个一次性 agent，且隔离 cwd / `DSH_HOME` / `DSH_AGENTS_HOME` | `runLoaderSmoke({ label, tempDirPrefix, binScript, configPath, binArgs, prepare, inspect, expectedExitCode })` | `packages/test-support/loader-smoke/src/index.ts`（范例：`examples/headless-agent/tests/keyless-smoke.e2e.ts`） |
| 行为级 e2e 范式（造 bug → 跑 agent → **外部**复跑测试断言世界状态） | `harness.ts` + `coding-task.e2e.ts` | `examples/headless-agent/tests/` |
| 零 token 的确定性回归（把一次真实会话录成回放） | `installLlmReplay(ctx, { file, ... })` + `assertConsumed()`、`deriveReplayScript` | `packages/test-support/llm-replay/src/index.ts` |
| 会话读取与统计 | `ctx.sessionPersistence.load()` / `ctx.sessionQuery.*` / `parseSessionLog` | 见 §3.4 |
| 批量限流 | `DSH_E2E_MAX_WORKERS`（默认 4）、timeout 120s、retry 2 | `vitest.e2e.config.ts` |

原则（`docs/testing.md`，建议照搬）：**验证世界，而不是模型的自我报告**；优先真实实现而非 mock；从真实入口路径测试。

→ 对本调研的含义：**“skill 有没有被用上”从会话事件里读；“skill 有没有起作用”从世界状态里读**（文件、测试、命令复跑），模型自己的总结不算证据。

并发注意：**每个 case 用独立 `DSH_HOME`**——多进程共用同一个 profile 目录会因 `cordis.yml` 回写互相踩踏。

### 6.1 目录建议

```
skill-eval/
  fixtures/<case>/workspace/          # 预置工作区（.dsh/skills/<skill>/ 或空）
  cases/<case>/probes.yaml            # 正例/负例/边界（沿用工具包 schema）
  profiles/eval.patch.yml             # 评测专用 patch（隔离 skill 根、关标题、定模型）
  runner/run.mjs                      # 逐探针跑 headless（并发 + 超时 + 重试）
  runner/transcript.mjs               # 多帧 zstd 解码 → 结构化事件
  runner/grade.mjs                    # 断言（路由/产物/终态/token）
  report/report.mjs                   # 路由矩阵 + lift + 成本 + 方差
  results/<date>-<git-sha>.json       # 基线快照
```

本次实测写的两个可复用脚本（可作 M0 起点，本次会话产物）：
- `D:\Games\robot\_probe_session.mjs` —— 多帧 zstd 解码 + 事件类型统计 + skill 调用检索；
- `D:\Games\robot\_probe_session2.mjs` —— 打印 `tool/call` / `tool/result` / `assistant/message(usage)` / `turn/end` 结构。
- 实测夹具：`D:\Games\robot\_evalscratch\.dsh\skills\ping-check\SKILL.md`（正例/负例各跑一次）。

### 6.2 关键实现点

1. **执行**：`spawn(node, [dshBin, '--profile', 'headless', '--patch', profilePatch, probe])`，cwd = fixture workspace，超时 kill，记录 exit code。
   （注意本机沙箱限制：Node 捕获子进程 stdout 需用默认 pipe——在 DSH 的受限沙箱下 `child_process` 管道会 EPERM；本 harness 建议在普通 shell/CI 下跑，或让 headless 直接写文件。）
2. **取证据**：优先 `ctx.sessionPersistence.load(id)` 或 `ctx.sessionQuery.readSession(id)`（一方 API，自动展开 packed chunk 行）；离线分析用 `createZstdFrameDecoder()` + `decodeStorageRecord`；**不要**用整文件 `zstdDecompressSync`（只解首帧，实测踩到）。
3. **断言**：
   - 路由：`events.some(e => e.type==='tool/call' && e.data.name==='skill' && JSON.parse(e.data.arguments).name===expect)`
   - 负例：`!events.some(e => e.type==='tool/call' && e.data.name==='skill')`
   - 加载成功：`tool/result` 文本含 `<skill_content name="expect">`
   - 终态：`turn.end.reason.kind === 'completed'`，否则标"截断/报错"并**单独分类**（不要混进"未触发"）
   - 产物：fixture 内文件断言 / 跑一次项目自带测试
4. **报告**：混淆矩阵（期望 × 实际）、每 skill 触发率 x/y、负例误触发清单、lift 表（有/无 skill）、成本（token/请求/墙钟）、稳定率（runs 间一致性）、失败分类（未触发 / 误触 X / 混触到 X / 会话错误 / 截断）。
5. **回归**：改 description 后只复测"原失败 + 相关负例 + 同族正例"子集；基线只与**自身历史**比 Δ（工具包治理原则：不做跨模块排名）。

### 6.3 分阶段

- **M0（0.5–1 天）**：`transcript.mjs` + `grade.mjs`；对 1 个 skill 跑通正例/负例；同时**标定轮数/步数上限与超时**（用一个长任务实测截断点），并确定会话目录定位规则（`DSH_HOME` 隔离 + `--<cwd slug>--` 映射）。
- **M1（1–2 天）**：批量 runner + 报告；把 `skill-test-kit` 的 `cross-boundary.yaml` 与各 skill 的 `probes.yaml` 直接搬过来跑基线。
- **M2（2–3 天）**：L2 任务级用例（fixture + 产物断言 + "无 skill"对照），出 lift 表；接 CI 只跑 L0 + 受影响子集。
- **M3（可选）**：写成一个 DSH 插件（daemon-loop 形态，定时对 skill 池做体检并把失败路由给 owner），或做成 web 面板展示路由矩阵。

---

## 7. 风险与待验证

- ~~错误路径的转录完整性~~ **已验证（§3.5）**：被 kill 的 run 仍留下 30 条事件（含 skill 目录注入与 `tool/call`），不需要额外的“证据恢复”机制；剩下的是报告口径问题——把异常终态与“未触发”分开统计。
- **轮数/步数上限**：headless 的步数上限与截断行为未定位到确切配置项（`--dump-config` 中未见显式 maxSteps 条目），需在 M0 用长任务实测标定，否则"未触发"里会混入截断。
- **缓存效应**：实测已见 `cacheReadTokens`（同工作区重复跑会被命中），重复跑要在报告里记录缓存状态，避免把缓存收益误读为稳定性。
- **DSH 与 Claude Code 的语义差**：Claude Code 的 `skillCalls` 元数据不存在；DSH 的等价证据是 `skill` 工具调用 + `<skill_content>`。工具包"负例必须在 skills:all 下跑"这一假设在 DSH 需重新定义（DSH 默认即全量目录，负例 = 零调用）。
- **`whenToUse` 不参与路由**（目录只含 name+description）：若把路由提示写进 `whenToUse`，等于没写——评测时可直接证伪。
- 外部生态数字（SkillsBench 等）本机无法抓正文，未采信。

---

---

## 9. 网上的最佳实践（本次已抓原文核对，附出处）

> 说明：本机 DNS 只能解析部分域名——`raw.githubusercontent.com` 不通，但 **`api.github.com` 可用**，因此下面这些结论是**读原始文件**得来的（不是标题猜测），原文已存 `D:\Games\robot\_web\files\`。唯一没取到的是 OpenAI 那篇博客（`developers.openai.com` 返回 403）。

来源仓库：

| 来源 | 是什么 | 关键文件 |
|---|---|---|
| [anthropics/skills · skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) | **官方**的 skill 创建 + 评测闭环（含评测 viewer、benchmark 脚本、描述优化器） | `SKILL.md`、`references/schemas.md`、`agents/{grader,comparator,analyzer}.md`、`scripts/{run_eval,aggregate_benchmark,run_loop,improve_description}.py` |
| [olaservo/skilljack-evals](https://github.com/olaservo/skilljack-evals) | 独立评测 CLI（多 runner：claude-code/codex/gemini/opencode），已把 SkillsBench 的口径产品化 | `README.md`、`eval.config.yaml`、`src/score/metrics.ts`、`src/score/oracle-gate.ts` |
| [benchflow-ai/skillsbench](https://github.com/benchflow-ai/skillsbench) | 学术型 benchmark（任务设计/审计规范） | `.agents/skills/task-creator/references/test-design.md`、`task-review/references/{policy-rubric,trajectory-audit}.md`、`docs/harnesses/README.md` |
| [addyosmani/agent-skills · evals](https://github.com/addyosmani/agent-skills/tree/main/evals) | 每个 skill 一个 case + fixture 的工程化范式 | `evals/README.md`、`evals/cases/*.json`、`docs/skill-anatomy.md` |
| [crashcartlabs/skill-testing](https://github.com/crashcartlabs/skill-testing) | 静态 21 项检查 + 行为检查 + 描述写作规范 | `eval/check-skill.sh`、`eval/behavioral-check.md`、`WRITING-DESCRIPTIONS.md` |
| [tony-adamson/groundwork-bench](https://github.com/tony-adamson/groundwork-bench) | 确定性评分 + rubric + LLM judge 的评测脚手架 | `bench/{rubric.md,judge.py,score.py}` |

### 9.1 官方闭环（Anthropic skill-creator，可直接照抄流程）

```
写草稿 → 造 2–3 条真实测试 prompt → 同一批次里同时跑【有 skill】和【基线】
       → 跑的同时写断言（不干等）→ grade → aggregate 成 benchmark
       → 给用户看（Outputs 页看产物 / Benchmark 页看数字）→ 收反馈 → 改 skill → 迭代
```

八条硬性做法：

1. **有 skill / 无 skill 必须同一批次一起跑**，不要先跑完一组再补另一组（"Launch everything at once so it all finishes around the same time"）。
2. **基线要选对**：新建 skill 的基线 = 无 skill；改进既有 skill 的基线 = **改之前的快照**（先把 skill 目录 `cp -r` 成 `skill-snapshot/` 再动刀）。
3. **产物目录约定**：`<skill-name>-workspace/iteration-N/<eval-name>/{with_skill|without_skill|old_skill}/outputs/`，eval 目录名要有描述性（不要叫 `eval-0`）。
4. **断言要客观可验证、名字要自解释**，且**能用脚本判就写成脚本**（"scripts are faster, more reliable, and can be reused across iterations"）；纯主观 skill（文案风格、美术）不要硬塞断言，交给人评。
5. **时序数据只有一次机会**：`total_tokens` 与 `duration_ms` 来自运行完成通知，必须当场落 `timing.json`，事后无法补。
6. **统计要带方差**：benchmark 汇总给的是 mean ± stddev + min/max + delta，而不是一个孤零零的百分比。
7. **人工评审是流程的一部分**，不是可选项：viewer 里逐条看产物 + 填反馈 → `feedback.json`；空反馈表示该条 OK，改动集中在用户点名抱怨的用例上。
8. **迭代到"没有实质进展"就停**（用户满意 / 反馈全空 / 再改没有有意义提升）。

### 9.2 评测产物 schema（官方字段名，别自己发明）

`evals/evals.json`（用例定义，放 skill 目录内）：
```json
{ "skill_name": "example-skill",
  "evals": [{ "id": 1, "prompt": "…", "expected_output": "…",
              "files": ["evals/files/sample1.pdf"],
              "expectations": ["输出包含 X", "使用了 script Y"] }] }
```

`<run-dir>/grading.json`（判分结果，**字段名 viewer 依赖，不能改名**）：
`expectations[{ text, passed, evidence }]` + `summary{passed,failed,total,pass_rate}` + `execution_metrics{tool_calls,total_tool_calls,total_steps,errors_encountered,output_chars,transcript_chars}` + `timing{...}` + `claims[{claim,type,verified,evidence}]` + `eval_feedback.suggestions[{assertion,reason}]`。

`benchmark.json`：`metadata{skill_name,skill_path,executor_model,analyzer_model,timestamp,evals_run,runs_per_configuration}` + `runs[]{eval_id,eval_name,configuration,run_number,result{pass_rate,passed,failed,total,time_seconds,tokens,tool_calls,errors},expectations,notes}` + `run_summary{with_skill,without_skill,delta}`（每个指标都是 `{mean,stddev,min,max}`）+ `notes[]`。

**官方工作区目录布局**（照抄即可）：
\`\`\`
<skill-name>-workspace/
  skill-snapshot/                    # 改旧版前 cp -r 的快照（当基线用）
  history.json                       # 改进轨迹
  feedback.json                      # 人工评审反馈
  iteration-1/
    <描述性-eval-name>/
      eval_metadata.json             # {eval_id, eval_name, prompt, assertions}
      with_skill/outputs/metrics.json
      without_skill/outputs/metrics.json     # 新建 skill 的基线
      old_skill/outputs/…                    # 改旧版时的基线（二选一）
      */run-<K>/{grading.json, timing.json}
    benchmark.json / benchmark.md
    comparison-N.json / analysis.json        # 仅盲测时
\`\`\`

**官方工作区目录布局**（照抄即可）：

```
<skill-name>-workspace/
  skill-snapshot/                  # 改旧版前 cp -r 的快照（当基线用）
  history.json                     # 改进轨迹
  feedback.json                    # 人工评审反馈
  iteration-1/
    <描述性-eval-name>/
      eval_metadata.json           # {eval_id, eval_name, prompt, assertions}
      with_skill/outputs/metrics.json
      without_skill/outputs/metrics.json   # 新建 skill 的基线
      old_skill/outputs/…                  # 改旧版时的基线（二选一）
      <config>/run-<K>/{grading.json, timing.json}
    benchmark.json / benchmark.md
    comparison-N.json / analysis.json      # 仅盲测时
```

`history.json`（改进轨迹）：`iterations[]{version,parent,expectation_pass_rate,grading_result(baseline|won|lost|tie),is_current_best}` + `current_best`。

→ 对我们最有参考价值的两点：**`grading_result` 只有 won/lost/tie 三态**（版本之间两两比，不做绝对分排名）；**每条 run 都记 tool_calls 与 tokens**，让"skill 是不是在白费功夫"可被看见。

### 9.3 指标口径（skilljack 实现，SkillsBench 同源）

`src/score/metrics.ts` 里全是纯函数，逐条抄：

| 指标 | 定义 |
|---|---|
| `resolutionRate(trials)` | 一个 task 多次试验的通过率（= 该 task 的成功率） |
| `passAtK(trials)` | 只要有一次通过就算过（k 次试验） |
| `binomialCI(p, n)` | **95% Wald 区间**：`p ± 1.96·sqrt(p(1−p)/n)`，clamp 到 [0,1]；n=0 时给 [0,1] |
| `skillLift(withSkillRate, baselineRate)` | 单 task：有 skill 成功率 − 基线成功率 |
| `macroSkillLift(lifts)` | 各 task lift 的**宏平均**（task 等权，不被高频 task 带偏） |
| `skillInvocationRate(invoked)` | 有 skill 试验中"真的调用了期望 skill"的比例；**调用方必须先剔除 expectedSkillLoad === 'none' 的任务**（反触发任务不进分母） |
| `groupMetrics(tasks)` | 按 difficulty/category/tags 分组算 resolutionRate 与 passAtK |

→ 直接回答了"该报什么数"：**resolution rate + 置信区间 + lift + 调用率 + 分组切片**，而不是"通过率 23/26"。

### 9.4 描述优化（触发率专项，官方有完整算法）

- **20 条 trigger eval**：8–10 条 should_trigger + 8–10 条 should_not_trigger，存成 `[{"query":"…","should_trigger":true}]`。
- 查询必须**像真人说话**：带文件路径、列名、公司名、缩写、小写、错别字、一点背景故事。官方给了正反例：
  - ✗ `"Format this data"` / `"Extract text from PDF"` / `"Create a chart"`
  - ✓ `"ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage…"`
- **负例必须是 near-miss**（共享关键词但要的是别的东西）。"给 PDF skill 写个 fibonacci 函数"这种负例毫无价值。
- 跑法：`python -m scripts.run_loop --eval-set … --skill-path … --model <当前会话模型> --max-iterations 5`；**60% train / 40% held-out test 切分，每条查询跑 3 次取稳定触发率**，每轮用失败样本让模型提出新描述，**最终按 test 分选 best_description（不是 train 分）以防过拟合**。
- 报告用 HTML viewer 给人看每轮变化。

### 9.5 一条被反复强调的机制性洞察（决定探针怎么写）

> Claude 只在**它自己搞不定**的任务上才咨询 skill。简单的单步请求（"读一下这个 PDF"）即使描述完美也可能不触发。

所以：**探针必须足够 substantive / 多步 / 专业化**，否则测的是"模型觉得这活需不需要帮手"，而不是"描述写得好不好"。这解释了为什么本机工具包会看到"含糊探针双峰 flaky"——那是探针的问题，不是模型的问题。

### 9.6 描述怎么写（crashcart 的 WRITING-DESCRIPTIONS + 官方一致）

- description 是**唯一触发机制**：正文只在触发之后才加载 → "正文满分、描述拉胯"的 skill 永远不会运行。
- 必须同时写清 **做什么 + 什么时候用**，所有 when-to-use 信息都放描述里，不要只放正文。
- **祈使句 + 第三人称**（"Reviews a diff and… Use when the user asks to…"）；出现 I/you 直接判 FAIL。
- 写**用户意图**，不写实现步骤。
- **至少 2 个具体触发条件**（≥2 concrete trigger conditions）。
- **要"pushy"但要"sharp"**：pushy = 语气上主动（对抗欠触发，官方也说"描述可以稍微 pushy 一点"，因为模型倾向 undertrigger）；sharp = 边界要准（对抗过触发）。反模式是"胆怯而窄"和"pushy 但含糊"。
- **不要枚举查询列表**：会膨胀且过拟合，触发不准时要**拓宽意图类别**，而不是加例子。
- 硬约束：**≤1024 字符**（超了会截断）、实质内容 **≥40 字符**、**不能含尖括号/XML**。目标 100–200 词。

> **对 DSH 的直接差异**：DSH 的 catalog 只截断到 `catalogDescriptionMaxLength`（**默认 500 字符**，见 §2.2），比 Claude 的 1024 更紧；写描述时要按 500 字预算来，并把这条纳入 L0 检查。

### 9.7 任务可解性门：oracle gate（防止坏用例污染评测）

skilljack 的 `validate` 子命令做的事值得照搬：在**全新的种子工作区**里跑 task 自带的 **oracle 参考解**，然后要求 task 自己的 verifier 给出 **reward = 1.0**；达不到就说明"这个任务要么无解、要么 verifier 坏了"，不许进入评测集。细节：verifier 走与正式运行相同的分发路径（含 docker 沙箱）；verifier 每次重新物化 contract 文件，防止 oracle 写下的 reward 泄漏进去。

→ 对应到我们：**每条探针在纳入基线前，先证明"期望结果可达"**（例如用一个已知正确的 agent 轨迹/手写产物跑一遍判据，判据必须给过）。

### 9.8 轨迹审计（怎么判定"真的用了 skill"）

SkillsBench 的 `trajectory-audit.md` 与 skilljack 的 invocation 口径一致：**从轨迹事件里判定是否调用了期望 skill**，并把反触发任务的调用率单独统计（更准确地说：反触发任务的指标是"误触发率"，不能混进调用率的分母）。

→ 与我们在 §3.4 的 DSH 判据完全对应：`tool/call.name === 'skill'` + `arguments.name === 期望值`，或用 `tool/result` 里的 `<skill_content name="X">` 作为"真的加载了"的强证据。

### 9.10 SkillsBench：benchmark 级规范（学术口径，含大量可机检的硬规则）

**任务包结构（强制）**：`tasks/<task-id>/{task.md, environment/{Dockerfile,skills/}, oracle/solve.sh, verifier/{test.sh,test_outputs.py}}`；命令 `bench tasks check <task>` → `bench eval run --tasks-dir <task> --agent oracle --sandbox modal`（本地用 `--sandbox docker`）。

**筛选目标**：任务必须是**多 skill 组合**（2+ skills），且 SOTA 模型得分 **<50%**（即"现在的模型还做不好"才值得进集）。

**硬规则**：

1. **Oracle 必须先通过才允许跑 agent**（"Oracle must pass before agent runs"）。
2. **prompt 里不得提及 skill**——必须让 agent 自己发现（否则测的是"照着指路走"）。
3. **测试条数上限**：官方统计"76% 的任务只有 1–5 个测试；>10 个需要理由"。按复杂度给目标：单输出 2–3、多步 pipeline 3–5、多独立输出 5–8、多约束复杂 8–10。"dense tests"是仅次于"AI 生成 prompt"的第二大 review 反弹原因。
4. **parametrize 不复制**：用 `@pytest.mark.parametrize` 表达多个 (locator, expected) 组合，而不是复制 N 个测试函数。
5. **exists + valid + correct 合成为一个测试**；每条断言必须带错误消息：`assert actual == expected, f"{coord}: got {actual}, expected {expected}"`。
6. **阈值必须先 profile 保存的产物（artifact）再定**，不是照抄指令文本——官方实测出"指令说删某列、artifact 里却保留"的分歧，结论是 **"作者保存的 artifact 才算数"**；不同 locator 用不同 `min_count`。
7. **反作弊**：测试必须 outcome-based，**禁止 grep 源码关键词/import 判断**；`/verifier/`、`/oracle/` 运行期对 agent 锁定；不从 agent 工作目录 import fixture；expected artifact 只放 `verifier/`；镜像里不得含 answer key。
8. **verifier 脚本经典坑**：reward 写入必须紧跟被测命令取 `$?`——`pytest ... | tee out; if [ $? -eq 0 ]` 里 `$?` 是 **tee 的退出码**，会让 reward **恒为 1.0**（静默失真）。正确做法：`pytest …; RC=$?`，把 reward 写进 `/logs/verifier/reward.txt` 后 `exit 0`。
9. **skill 数量**：**2–3 个/task 最优，4+ 收益递减**；skill 必须经 `--skill-mode with-skill --skills-dir` 部署，不能靠 Dockerfile copy。
10. **评分档**：APPROVE（oracle 100% 通过 + agent 带 skill 通过 + 无政策问题）/ APPROVE WITH CAVEATS / MAJOR CHANGES NEEDED（测错东西、skill 反而降性能、跨 trial 高方差、环境坏）/ REJECT。并明确 **skills-utilization 是 additive**——强模型不用 skill 也能过，这是可接受的，不因此判定 skill 无价值。

**轨迹审计**：读 `trajectory/acp_trajectory.jsonl`（事件 `user_message / agent_thought / tool_call / agent_message`；每个 `tool_call` 带 `kind ∈ {read, edit, execute, search, other}` 与自由文本 `title`），**不要读"agent transcript"**；oracle job 是机械的、跳过；每个 agent job 产出 `audit-<config>.json`（含 SB-1 invocation verification、SB-2 跨轨迹 skill-impact delta、SB-3 skill 误用）。harness 差异必须记录（源码版本、文档出处、实跑轨迹三选一取证），**源码转私有或迁移后该条结论要标 `needs reverification`**。

### 9.11 静态门与作者自查清单（可直接进 CI）

crashcart 的 `eval/check-skill.sh` 是一份**现成的 21 项检查实现**（643 行，FAIL 阻断 / WARN 不阻断，FAIL=0 才 exit 0）。最值得抄的判据：

| # | 检查 | 级别 |
|---|---|---|
| 1–2 | frontmatter 首行 `---`、YAML 可解析为 mapping；`name` ≤64、`^[a-z0-9-]+$`、不得含 `anthropic`/`claude`/`<>` | FAIL |
| 3 | **`name` 必须等于目录名** | FAIL |
| 5–6 | `description` 非空、≤1024 字符、无 XML；**第三人称**（不得以 `I `/`you `/`we ` 开头，不得含 `i can`/`you can`/`i will`/`i'll`…） | FAIL |
| 7/7b | 必须含真触发短语（`use when`/`use for`/`when the user`/`when working`/`when asked`/`triggers when`），且其后**≥2 个具体条件**（按逗号/`or` 切分计数） | WARN |
| 9 | SKILL.md 正文 **≤500 行** | WARN |
| 10 | 不得出现 Windows 反斜杠路径（可逐行 `allowlist windows-path` 豁免） | FAIL |
| 13 | 全树扫描密钥：`sk-[A-Za-z0-9_-]{16,}`/`ghp_[A-Za-z0-9]{30,}`/`AKIA[0-9A-Z]{16}`（逐行 `allowlist secret` 豁免） | FAIL |
| 12 | 安全气味：`curl … \| sh`、`rm -rf`、`base64 -d`、`curl -X POST` | WARN |
| 14 | **`tests.md` 必须带 `Last verified: YYYY-MM-DD`，且 H2 场景 ≥3**；距今 >90 天告警 | FAIL/WARN |
| 16–20 | 参考 .md ≤200 行、>100 行须有 `## Contents`、不得散落在 SKILL.md 旁、**每个参考文件都必须被 SKILL.md 链接（无孤儿）**、引用只一层深 | WARN |
| 21 | 若存在 `staging/<name>` 孪生目录，对共有文件 `diff -q` 报分叉（防"改了 live 忘了 staging"） | WARN |

配套：linter 自身有 10 个 fixture 自测 + 26 个 pytest 用例；CI 要求 `examples/` **0 FAIL 0 WARN**、live 与 staging **0 FAIL**。**注意分级**：crashcart 只把 `check-skill.sh` 当硬门，value-add/触发率是"里程碑咨询项"，不是每次编辑的硬门。

> **写成 skill 的硬结构经验**（addyosmani）：frontmatter 只放 name + description，**不要在 description 里摘要工作流**（模型会照摘要走而不读正文）；正文推荐章节 = Overview → When to Use（含 *NOT for Y*）→ Core Process（编号步骤 + 决策点）→ Specific Techniques → Common Rationalizations（借口 \| 事实反驳两列）→ Red Flags → Verification（可勾选、每条要有证据）；参考材料 >100 行拆文件、<50 行留 inline、正文 <500 行、**引用只一层深**、能写成脚本就写成脚本（脚本只在输出时耗上下文）。

### 9.12 其他值得直接抄的机制（来自 4 个来源的交叉验证）

1. **Canary 断言**：放一条**固定必挂的假断言**（`eval-canary/grading.json`），正确判分器必须判它 FAIL；若判 PASS，**整轮数字作废，先修判分器**。
2. **Fails-closed 聚合**：任何 case 还处于 PENDING、或 canary 没判 FAIL，聚合脚本**非零退出且不写文件**；禁止手算汇总。
3. **作者 ≠ 评分者；语义断言必须盲评**（把两份输出脱标识交给独立判官）。
4. **CI 分层**：Tier1 硬（每次 PR/push，只做**形态校验**：结构、case 文件存在、查询格式）；Tier2 软（每周定时 + 手动触发，**不得**成为 required PR check）；Tier3（真·通过率门禁）在把 flakiness 与成本基线摸清之前**不做**。
5. **触发门用 rank-1**（正样本把自己排第一的比例），基线 100% 时门设 **95%**，**只准上调不准下调**；**描述碰撞检测**：两两描述相似度 ≥75% 判 error、≥50% warn。
6. **复合分与"回滚地板"**：`score = 0.4·trigger + 0.4·quality + 0.2·efficiency`，**harness FAIL 时 score = −∞**（无条件回滚，构成"最佳实践地板"）；`efficiency = min(1, baseline_tokens / candidate_tokens)`（越慢越多耗则不得分，权重压到 0.2 防主导）。
7. **迭代留痕**：`results.tsv` 每行 `iter score trigger quality tokens harness kept edit_summary`，`kept=yes/no`，每个保留迭代一个 commit——**改进过程本身可审计**。
8. **结果四象限读法**（比看均值有用得多）：两臂都过 → 该断言无信号，换掉；两臂都挂 → 修或删；**只有 with-skill 过 → 这就是 skill 的价值点，必须搞懂是哪条指令起的作用**；重复间高方差 → flaky 用例或指令含糊，收紧它。
9. **压力用例**：纪律型 skill 要额外加"时间压力 / 沉没成本 / 权威压力"三类对抗性 prompt。
10. **成本与收益必须一起报**：官方 benchmark 把 `tokens` 与 `time_seconds` 和 pass_rate 并列进 `run_summary` 与 `delta`——"skill 让成功率 +50% 但平均多花 13 秒、+1700 token"这种句子才是有用的结论。
11. **证据分级**（rhyanvargas）：Live observation > Authoritative reference > Recorded context > 模型记忆 > 模型知识；**一条断言的强度 = 它引用源里最弱的那个**，高风险结论（PR 正文、changelog、放行/阻断判定）必须用更高级证据。

### 9.14 工程化细节（skilljack / groundwork / rsc 的实现级做法）

**配置与目录契约**（skilljack `eval.config.yaml`）
- 优先级：默认 → `eval.config.yaml` → `EVAL_*` 环境变量 → CLI flag。
- 关键默认值：`runner.timeout_ms: 300000`（agent）、verifier `60000`、judge `300s`；`concurrency: 1`；`thresholds.resolution_rate: 0.8`；`judge_truncation: 5000`、`report_truncation: 2000`；`cache: {enabled, dir, ttl_hours: 168}`；`ci.exit_on_failure: true`。
- 任务目录（**强制约定**）：`evals/<task-id>/{task.md, environment/skills/<name>/, environment/workspace/, environment/Dockerfile, verifier/verify.mjs, oracle/solve.mjs}`。
- `task.md` frontmatter：`id`（**必须等于目录名**）、`difficulty: easy|medium|hard`、`category`、`tags`、`expected_skill`（`none` 是保留字）、`expect_skill_invocation: true|false`（false = **反触发任务**）、`timeout_ms`、`verifier{timeout_ms,command}`、`checks`（`contains/not_contains/regex/marker/tool_calls/no_tool_calls/files_exist/javascript`）。
- 试次工作区：`<output>/workspaces/<taskId>/run-<n>/`；`--keep-workspaces all|failures|none`（默认 failures，便于事后取证）。

**verifier 契约**：cwd = 试次工作区；环境变量 `SKILLJACK_OUTPUT_FILE / SKILLJACK_TRAJECTORY_FILE / SKILLJACK_TASK_DIR / SKILLJACK_REWARD_FILE`；reward 写文件（0..1 浮点），否则退回 exit code（0→1）；按扩展名派发 `.mjs/.js → node`、`.py → python`、`.sh → bash`、`.ps1 → powershell`。

**打分器分层（重要且与直觉相反）**
- skilljack：**deterministic reward 是唯一权威**——reward=1 当且仅当全部 checks 通过且 verifier reward ≥ 1；agent 报错/超时 = 0；**judge 永不改 reward**（只做诊断）。
- groundwork：`final = 0.7·deterministic + 0.3·judge`，judge 失败时退化为纯 deterministic。
- rsc 的建议配比：**约 60% 确定性 / 30% judge / 10% 人工**，统一接口 `Scorer.score(case, output) → 0.0~1.0`。

**指标与门禁**：Resolution Rate（每任务试次通过率均值，95% 二项 CI）、Pass@k（`--trials` 默认 **3**）、Skill Lift（with − baseline，逐任务 + macro）、Skill Invocation Rate（剔除反触发任务；`expect_skill_invocation:false` 的任务**一旦调用即判失败**）；门：`--threshold-resolution`（默认 **0.8**）与 `--threshold-lift`（**fail-closed**：配了 lift 阈值却没有 baseline 直接失败）。报告产物 md/json/html + `summary.json`；**judge 诊断独立分区、永不 gate**，并把失败归因成五类：`discovery_failure / false_positive / instruction_ambiguity / missing_guidance / agent_error`。回归：`--compare-results` 与上次 summary diff 出 `has-regressions`；groundwork 用 `baseline.json` + `--tolerance`（默认 0.05），跌破即非零退出；rsc 主张**对 committed baseline 做回归门禁而不是绝对阈值**，用 bootstrap CI 吸收 judge 噪声——**只有跌出 CI 的下降才算回归**，并实测"单次运行两个 agent 统计上不可分，比较需要 3–5 次重复 + 固定 judge 模型"。

**缓存与并发**：缓存是**内容寻址**，key = `{task, prompt(+nudge), model, runner, skills hash, environment hash, timeout, trial index}` → **改了 skill 自动失效**；有 verifier / workspace 种子 / `files_exist` 的任务**绕过缓存**；`--skip-cache/--bust-cache/cache clear`、ttl 168h。

**沙箱**：`--sandbox docker` **只容器化 verifier，不容器化 agent**（workspace→`/workspace`、task→`/task`、日志→`/logs`）；verifier 写 `/logs/verifier/reward.txt` 优先生效；`environment/Dockerfile` 按内容哈希只构建一次。

**多 runner 抽象与"怎么算调用了 skill"**（各家判定方式不同，这是跨 harness 不可比的根源）：Claude 系看 **Skill 工具调用**；codex 看 **shell 读 SKILL.md**；gemini/opencode 看 `activate_skill`/`skill` 工具 + SKILL.md 兜底。skill 挂载路径也各不相同（`.claude/skills`、`.agents/skills`、`.gemini/skills`、`.opencode/skills`）。

**rubric 与 judge 的确定性技巧**（groundwork）
- rubric 三维各 1–5 整数：completeness（关键文件/入口/技术栈覆盖）、accuracy（无虚构文件/框架）、evidence（文件路径、符号、引用代码、`FACT/INFERENCE/UNKNOWN`）；要求"只回一个 JSON 对象"。
- judge 提示模板：rubric + `----- ARTIFACT UNDER REVIEW -----` + 报告 + `----- END ARTIFACT -----` + "Return only the JSON object"。
- **解析要确定性**：括号深度计数取第一个平衡 JSON 对象，失败就从下一个 `{` 重试；分数容忍裸数字、`int()` 后 clamp 到 [1,5]、再 `avg/5.0` 归一化。
- 确定性打分 = 小写 + 空白折叠的子串匹配，每项配"可接受的替代表述"列表；权重按维度给（如 `must_mention_files 0.4 / entry_points 0.3 / stack_facts 0.3`）；`hallucination_traps` 每命中扣 0.1，并配否定词窗口（`no`/`does not use`/`absent`）防误伤。
- **避免自评**：`--judge-agent codex|claude|custom|none` —— 判分模型要与被测模型不同源。
- 成本边车文件：`{cost_usd, input_tokens, output_tokens, cache_read_tokens, reasoning_tokens, turns}`，wall time 恒测；缺文件时相应字段为 `null`（**不要伪造 0**）。

**judge 校准（rsc，最容易被忽略的一环）**
- 数据集：**每类失败模式 50–200 条人工标注**样本，**禁止纯合成**，JSONL 进 git 并做去污染；case schema `{id, input, expected, context, meta:{failure_mode, source}}`。
- judge 模型能力 **≥ 被测系统**；**先写 rationale 再给分**（可把 judge–human 一致率推到约 85%）；**pairwise 优于 pointwise**（1–10 单点分数会挤在 8–9）；**交换 A/B 位置再平均**以抵消位置偏见；上 gate 之前先报告**与人类 gold 的一致率 / Cohen's kappa**。
- gate = bootstrap CI + `eval-report.json`（metrics、per-failure-mode slices、baseline、pass/fail），回归则非零退出。
- 反模式 8 条：vibes 门禁、纯合成集、未校准 judge、judge 弱于系统、绝对阈值门、**按排行榜数字上线（harness 效应可差 10–20 分）**、只评终答不评轨迹、gold 长期不重标。

**harness 最佳实践 10 条**（B 组结论，与 9.12 互补）：① deterministic reward 权威，judge ≤30% 或仅诊断；② 先跑 oracle gate；③ 配 baseline 算 lift，别只压绝对门槛；④ k≥3 trials + Pass@k + 95% CI，比 agent 要 3–5 次重复；⑤ 内容寻址缓存（含 skills/environment hash）+ 并发上限；⑥ ground truth 与 agent 隔离（答案键不入 fixture）；⑦ judge 强制 JSON schema + 平衡括号解析 + clamp 归一化 + 先理由后分数；⑧ 盲化 + 位置交换 + 判分模型不同源；⑨ 回归门对 committed baseline + bootstrap CI，fail-closed；⑩ 产物机器可读且带元数据（runner/model/wall_seconds/cost_usd/tokens/turns），golden set 定期重标。

### 9.15 官方三个子 agent 的分工与判据（可直接照抄的实现细节）

Anthropic skill-creator 用三个独立子 agent 承担三件不同的事，**别用一个"打分器"糊过去**：

| 子 agent | 何时用 | 输入 | 输出 | 判据要点 |
|---|---|---|---|---|
| **grader** | 每轮必用 | `expectations[]`、`transcript_path`、`outputs_dir` | `grading.json` | PASS 必须**引用原文证据**且体现"真实完成"而非表面合规（文件名对但内容空/错 → FAIL）；**无部分分**；**不确定时举证责任在断言**（"the burden of proof to pass is on the expectation"）；除判分外还要**反过来批评评测本身**（"错了也能过"的断言、没有任何断言覆盖的重要结果）；另外抽取并核验 claim（`factual/process/quality` 三类），核不了的显式标注 |
| **comparator** | 要判"新版是否真的更好" | 两份**匿名**输出 + prompt（+ 可选断言） | `comparison.json{winner:A\|B\|TIE, reasoning, rubric, output_quality}` | 盲态（不知谁产出的）；rubric 两维各 1–5：content（correctness/completeness/accuracy）与 structure（organization/formatting/usability），维度取均值，overall 换算成 1–10；**优先级：rubric 总分 > 断言通过率 > TIE**；除非真正等价否则必须选出胜者 |
| **analyzer** | ① 解释"为什么赢" ② 读 benchmark 出观察 | ① winner/loser 的 skill 路径+transcript+comparison 结果 ② `benchmark.json` | ① `analysis.json{comparison_summary, winner_strengths[], loser_weaknesses[], instruction_following{winner/loser:{score,issues[]}}, improvement_suggestions[{priority:high\|medium\|low, category:instructions\|tools\|examples\|error_handling\|structure\|references, suggestion, expected_impact}], transcript_insights}` ② 一组 notes 字符串 | **benchmark 模式禁止给改进建议或主观质量评价，只做观察**；改进建议只在对比模式里给，且必须带优先级与类别 |

**run_eval.py（触发率测量器）**：`--num-workers 10 --timeout 30 --runs-per-query 3 --trigger-threshold 0.5`；判定方式是从 stream 事件里**早停**（遇到 `Skill`/`Read` 工具才继续累积参数，出现其它工具立即判 False）；`trigger_rate = 命中次数 / 运行次数`，should_trigger 时 `pass = rate ≥ 0.5`，should_not_trigger 时 `pass = rate < 0.5`。**无 cache、无重试**。

**aggregate_benchmark.py**：`pass_rate` 取自 grading.summary；`time_seconds` 取自 grading.timing（为 0 时回退读 `timing.json`）；`tokens` **缺失时回退用 output_chars**；统计量 mean/stddev/min/max，**stddev 用 n−1 样本方差**；`delta` 是两配置均值差（`+0.50`/`+13.0`/`+1700`）；`runs_per_configuration` **硬编码为 3**；脚本只出数字**不下结论**，结论由 analyzer 的 notes + 人读。

**improve_description.py（描述优化器的信号）**：只吃**双侧失败样本**——`failed_triggers`（应触发没触发，FN）与 `false_triggers`（不该触发却触发，FP），每条附 `triggered x/y times`；把当前描述、train/test 分数、失败样本、历史（附 "do NOT repeat these — try something structurally different"）一起喂给模型，输出用 `<new_description>` 包裹后正则抽取；**目标 100–200 词、硬上限 1024 字符**，超限自动重写一次。**本脚本不做验证**——验证交给 run_loop 在 train+test 重跑、按 **test 分** 选最优。

**几个容易踩的官方"硬约束"**：`grading.json` 的 `expectations` **只能**用 `text/passed/evidence` 三个字段名（换名字 viewer 直接空）；`benchmark.json` 的 `configuration` 只能 `"with_skill"`/`"without_skill"`，且 `pass_rate` 必须嵌在 `run.result` 下；**必须先跑 viewer 让人类看结果、再做自己的评估**；更新既有 skill 必须保留原名（不许 `research-helper-v2`）；**禁止用 `/skill-test` 之类的现成测试 skill 代替评测流程**。

**官方明确点名的反模式**（原文措辞）：不要写"fiddly、overfit"的改动；不要用全大写的 ALWAYS/NEVER 和僵硬结构；不要自己搓 HTML viewer；如果 3 个用例都各自重写了一遍 `create_docx.py`，说明**该把它固化成 `scripts/` 里的脚本**；Claude.ai 环境没有 subagent 时应跳过 baseline 与定量 benchmark。

> 需要清醒认识的一点：**官方这套工具只做到 mean/stddev/delta，没有置信区间、没有 kappa、没有 pass@k、没有回归门禁**（`run_eval.py` 连 cache 都没有）。统计严谨度是 skilljack / rsc / groundwork 那一档补上的——两边合起来才是完整的最佳实践。

### 9.13 与我们方案的差异（读完这些之后要改的五件事）

1. **DSH 的 description 预算要按 500 字符**（catalog 截断）而不是 Claude 的 1024——L0 与描述优化器都要按 500 来。
2. **我们的 L1 应该升级成"两臂配对 + 3 次重复 + 置信区间 + lift"**，而不是只报命中率；反触发任务的调用率单独统计（skilljack 的 `skillInvocationRate` 明确要求剔除 `expectedSkillLoad === 'none'`）。
3. **需要补两道"防自欺"工序**：canary 断言 + 聚合 fails-closed；以及"作者 ≠ 评分者 / 语义盲评"。
4. **判分结果的文件 schema 照抄官方**（`grading.json` 的 `expectations[{text,passed,evidence}]`），别自创字段名——将来若想接官方 viewer / 换工具，零迁移成本。
5. **CI 只上"形态校验"这一层硬门**：结构、`evals/` 文件存在、trigger 查询格式；真·通过率门禁要等 flakiness 与成本基线摸清之后再上（三份材料一致结论）。

### 9.9 反模式清单（各家反复点名）

1. 只有最终输出、没有轨迹 → 无法区分"用了 skill"和"碰巧答对"。
2. 只有绝对值、没有基线 → 无法回答"skill 到底有没有用"。
3. 只跑一次 → 方差当成结论（官方 benchmark 明确要求 runs_per_configuration，例子里是 3）。
4. 负例太容易（"给 PDF skill 写 fibonacci"）→ 什么都没测。
5. 断言能被"提到了关键词"骗过（`The output includes the name 'John Smith'` → 幻觉文档也能过；官方 grader 会主动提这类 `eval_feedback`）。
6. 把主观质量硬编成断言 → 只能靠 LLM 裁判，且必须先写好 rubric。
7. 任务本身无解 / verifier 有 bug → 用 oracle gate 先挡掉。
8. 只看 pass rate 不看 token/时长 → skill 让模型多花 3 倍 token 换 5% 提升，也该被看见。

---

## 10. 多轮对话型 skill 怎么评（设计）

### 10.1 先说硬约束（都是本次实测/原文确认）

- **headless 是"单轮盒子"**：官方 README 原文 —— "One submitted task only / the runner has no interactive follow-up surface"，它只提交一条用户消息、等到 idle、打印最后一条 assistant 文本。
- **headless 里连提问工具都没有**：我实测让模型"用 ask_user_question 问我 A 还是 B"，模型的回答是"**当前会话中没有 `ask_user_question` 工具**"——`--dump-config` 也确认只挂了 `user-questions` 服务，没挂 `dsh-tool-ask-user` 工具。
  → 所以"提问型 / 多轮型 skill"**在现成 headless 上根本跑不完**，这不是配置问题，是形态问题。
- 好消息：多轮的**驱动原语**是现成的——`Agent` 接口上有 `followup(msg)` / `steer(msg)` / `inject(msg)` 与 `await whenIdle()`；官方测试里的 `runFixtureTurn()` 就是"造一条 user message → followup → 收事件 → 等 idle"这四步，**多轮 = 把这四步放进一个 for 循环**。

### 10.2 三档处理（按成本从低到高，默认走 A+B）

| 档 | 做法 | 能测什么 | 不能测什么 |
|---|---|---|---|
| **A 单轮化**（默认兜底，覆盖多数用例） | 把多轮历史**预置进夹具**（`conversation.md` 或预置会话转录），用单轮 headless 只跑"第 N 轮" | 指令遵循、产出质量、基于既有上下文的决策 | 测不到"它会不会主动提问 / 何时停 / 怎么追问" |
| **B 自建 eval-runner 多轮驱动**（主力） | in-process `boot()` + `agents.create()/resume()`，用 `followup()` + `whenIdle()` 逐轮喂用户消息；用户侧用**脚本用户 + 答案银行** | 完整多轮行为：提问时机、澄清质量、是否复用用户给的答案、收敛轮数 | 真实人类的临场发挥（不需要） |
| **C LLM 用户模拟器 / 人工**（web profile） | 给用户模拟器 persona + 目标 + 停止哨兵；或干脆人工点 | 开放式对话质量、说服/协商类 | 确定性（**只能当 L2**，必须重复 + rubric，或按"人工评审豁免"处理） |

**B 档的两个关键细节**：

1. **答案银行按"槽位/意图"匹配，不按轮次索引**。多轮 killer 是"轮次漂移"：skill 让模型多问了一轮，脚本就答错了。所以脚本写成 `{slot: 'deadline', answer: '下周五'}`，用意图匹配应答；匹配不到就按"默认推进"话术，并记一次 `unscripted_turn`。
2. **要顺带把"提问链路"补回去**：在 runner 里挂上 `dsh-tool-ask-user` 并注册一个假的 `ctx.userQuestions` provider（返回脚本答案），这样提问型 skill 走的是**和 web 上一样的工具路径**，而不是被 `NO_PROVIDER` 打断或干脆没有工具。

### 10.3 多轮怎么判分（DSH 的结构优势）

DSH 的事件天然带轮号（`turn/start`、`tool/call.data.turn`、`step/end`），所以断言可以**按轮写**：

```yaml
turns:
  - must_ask_question: true      # 第 1 轮必须先澄清
    forbid_tools: [read, write, pwsh]   # 且不得先动手
  - must_use_slot: deadline      # 第 2 轮必须用上用户给的答案
    must_not_reask: [deadline]   # 不得重复追问同一个槽位
limits:
  max_turns: 6
  max_clarifying_turns: 2        # 防"无限追问"这个真实失败模式
  per_turn_timeout_ms: 120000
```

指标除了成功率，还要记 **turns-to-completion**、**clarifying turns**、**每轮 token**、以及 A/B 的"多花了几轮"——一个让模型多问 3 轮才动手的 skill，即使最终产出一样，也应该在报告里显示为代价。

### 10.4 工程注意

- **A/B 公平**：两臂用同一份用户脚本 + 同一答案银行；轮数不同不影响可比性（因为答案按槽位匹配），但要把轮数差计入报告。
- **防卡死**：多轮跑批必须有 `max_turns` + 每轮超时 + 全局墙钟；否则一个"引导用户无限澄清"的 skill 会把批量跑拖死。
- **缓存**：第 2 轮起前缀可命中 KV cache（实测第二步 `cacheReadTokens: 8064`），成本远低于 N×单轮，但仍要按"请求数"记账。
- **确定性回归**：把跑成功的多轮轨迹录成 `llm-replay` 夹具，之后零 token 复跑，专门盯"改动 skill 后多轮行为有没有退化"。

## 11. 已实现的一版（v0.1）与实测结果

代码在 `D:\Games\robot\skill-eval\`（详见其 `README.md`）：一个替换掉 `headless-runner` 的 DSH 插件，
用 `agent.followup()` + `await agent.whenIdle()` 逐轮驱动脚本用户，并补上 `ask_user_question` 工具与脚本化的
`userQuestions` provider。**5 次真跑的结果**：

```
oracle gate: 3/3 OK（正向控制：合成产物能过；负向控制：canary 必挂）——0 token

canary-never      with_skill  0/3  rate=0  wilson=[0,0.562]
clarify-multiturn with_skill  3/3  rate=1  wilson=[0.438,1]  wall= 7.7s  tokens=10,234
                  without     0/3  rate=0  wilson=[0,0.562]  wall=28.8s  tokens=14,222   lift=1
clarify-scripted  with_skill  3/3  rate=1  wilson=[0.438,1]  wall=10.5s  tokens=10,935
                  without     0/3  rate=0  wilson=[0,0.562]  wall=74.0s  tokens=24,070   lift=1

macro lift = 1 | canary = ok | 15 次运行合计 204,191 token
```

**顺带发现**：3/3 全过时 **Wald 95% CI 会退化成 [1,1]**——"看起来绝对确定"，实际 n=3 什么都证明不了。
skilljack 用的就是 Wald，所以照抄口径时要额外并报 Wilson（本例 [0.438,1]）或 bootstrap。
另外"无 skill 臂"不仅做不成事，还要多花 **3–7 倍时间与 1.4–2.2 倍 token**（74s/24k vs 10.5s/10.9k），
**所以报告必须同时给成功率、时长、token 三列**，否则会把"skill 只是慢"当成结论。

**四个实现级发现**（前两个是 DSH 事实，后两个是评测方法教训）：

1. **headless 连提问工具都没有**：实测让模型用 `ask_user_question`，它回答"当前会话中没有该工具"；
   `--dump-config` 确认只挂了 `user-questions` 服务、没挂 `dsh-tool-ask-user` 工具。多轮 + 提问必须自己搭。
2. **overlay 里新增条目必须放进 `insert:` 列表**：直接写 `- id: 新名字` 会被当成"按 id 改已有条目"，报
   `patch: entry "..." not found`，而**这个错误不会让启动失败**——一次性 runner 被关掉后无人退出，进程会安静地挂住。
   同理，插件跑完必须自己保证退出（本版在 `appExit` 之后加了 3 秒兜底 `process.exit`）。
3. **夹具污染会把"没有 skill 也行"变成结论**：第一轮批量跑时夹具里残留着上一次的 `plan.md`，
   于是**两个臂都 PASS、lift=0**——看起来像"这个 skill 没用"，实际是断言被上一次的产物满足了。
   对策：用例声明 `artifacts`，跑前检查夹具干净，脏了就报错退出（已实现）。
4. **"两臂都过"必须当成断言缺陷而不是结论**：同一批里 `clarify-scripted` 的无 skill 臂曾经以 40+ 次工具调用、
   182 秒"通过"了一条本不该通过的断言——这正是官方/ skilljack 反复强调的"断言无区分度就换掉"。

**成本参考**：with_skill 臂 13–15s、9k 输入 token 量级；without_skill 臂因为会乱找一圈，26–236s 不等
（**所以报告里必须同时给时间与 token，否则会得出"skill 只是慢"的错误印象**）。

**尚未实现**（下一版）：oracle gate、3 次重复取多数、混淆矩阵与 mean±stddev 聚合、并发与 `DSH_HOME` 隔离、
结构化产物断言（现在只有存在性 + 子串）、LLM 用户模拟器（C 档）。

## 12. 同类工具对照：alibaba/skill-up 与 agentut（原文核对）

两个都是真实存在、可用的项目，原文已抓到 `D:\Games\robot\_web\files2\`。

| | **alibaba/skill-up** | **agentut（Agent UT）** |
|---|---|---|
| 定位 | Agent Skill 的**评测 + 演进** CLI（Apache-2.0，Go ≥1.25，888★） | 给 **opencode** agent 工程做**单元测试**的 CLI（TypeScript，npm `agentut@1.4.x`） |
| 核心理念 | agentskills.io 官方评测循环的产品化：声明式 YAML → 多引擎执行 → 评分 → 结构化报告 → 由分发式 Skill `skill-upper` 驱动改进 | **"只记录输入，不记录响应"**：YAML 只存用户输入序列 + 断言，每次用最新 Skills 从头重放 |
| 支持的引擎 | `claude_code` / `codex` / `qodercli` / `qwen_code` / **custom（local\|http）** | 仅 `opencode`（claude/gemini 标注"未来支持"） |
| 用例格式 | `evals/eval.yaml`（入口）+ `evals/cases/*.yaml`（文件名即 case id）+ fixtures；**兼容 Anthropic `evals.json`（`--auto` 直接吃，`import` 转换）** | 单 YAML：`environments` + `scenarios[].steps[]` + `config` |
| A/B 两臂 | `benchmark.enabled`（`--baseline` 临时开）→ 输出 `<case>/with_skill/` 与 `without_skill/`，产出 `grading.json`（Anthropic 兼容）+ `benchmark.json` | 无"有/无 skill"两臂概念（它是给单仓库的 skill 写测试） |
| 多轮 | `input.turns[]`，**真会话 resume**：turn1 `Agent.Run` 建会话，turn2..N `SessionResumer.RunTurn`；claude_code `--resume`、codex `codex resume <thread-id>`；不支持的引擎**拼接成单条 prompt 回退**（且仅当无 post_condition/capture/每轮规则时允许） | 同场景多 step **共享会话**（多次 `opencode run --dir ...` 续跑），无轮级闸门 |
| 轮级机制 | `post_condition{must_contain_all\|any, must_not_contain, on_fail: fail\|skip_remaining}` + `capture{variable, pattern\|jsonpath}` → `{{var}}` 注入后续轮；轮级断言 `turn_response_contains` / `tool_called_in_turn` 等 | 每 step 独立断言；跨 step 无显式传值机制 |
| 判分 | 双层：`expect`（零成本闸门，失败即跳过 judge）+ `judge`（`rule_based` / `script`（退出码 + env 注入 final_message/transcript）/ `agent_judge`（criteria + `pass_threshold` 默认 0.7）） | 7 种断言（`should_call_tool` / `should_not_call_tool` / `should_produce_file` / `file_content_contains` / `response_contains` / `exec_command` / `judged_by`）+ Matcher（equals/contains/containsOneOf/regex/oneOf）；AI 裁判返回 `{score, reason}` |
| 统计 | `benchmark.json` 只给 `pass_rate / time_seconds / tokens` 的 **mean 与 delta**；**无方差、无置信区间** | `runs`（默认 5）/ `min_pass`（默认 4）概率判定；断言级 `min_pass`、`AssertionStat.pass_rate`；场景 0–100 分（断言分或裁判分）× priority 加权 |
| 防假绿 | 无 oracle / canary | 无 oracle / canary；有 mock 未命中 warning |
| 证据 | `collect_artifacts`（成功/失败/超时都收集，保留相对路径，排除 `.git/`）、`report.artifacts:[transcript]`、`--event-log` JSONL 实时流、OTLP | 每 run 完整对话进 `runDetails`；四种报告格式（json/markdown/html/jest） |
| 独特能力 | `context.repo_fixture` + `git.apply_diff`；MCP `real\|mocked` 及 per-case 覆盖；`requested/applied/observed_configuration` 三态（承认"配置≠实际生效"）；`validate` 全量校验；Docker/OpenSandbox 隔离；GitHub Action（镜像按 digest 锁定） | **distiller/suggest**：从真实 opencode session 蒸馏出测试（按 user 消息切 step，抽工具调用/文件变更/响应），`--no-llm` 走规则引擎；**mock 注入**（参数无害化 + `_agentutOriginalInput` 还原 + 未命中告警）；`initial_session` 导入真实会话做种子；给裁判的 **fact-only 摘要**（代码注释明确"不含任何指令"，抗注入） |
| 演进 | 无自动修复器；由 `skill-upper` skill 在对话里读失败 → 改 SKILL.md 或修 eval → 补用例 → 重跑（人 + agent 判断） | 无 |

### 12.1 结论：谁该用哪个

| 你的目标 | 建议 |
|---|---|
| 评 **DSH** 的 skill | 继续用本项目这套（原生多轮 + 会话事件证据），把 skill-up 的 `post_condition`/`capture`/`expect` 合并规则/三态配置/`collect_artifacts`/ERROR-FAIL-SKIP 分类抄进来 |
| 评 **Claude Code / codex** 的 skill | **直接用 skill-up**（原生支持这两个引擎 + GitHub Action + 直接吃 Anthropic `evals.json`），不要自己造 |
| 评 **opencode** 的 skill | **直接用 agentut**（原生 opencode + session 蒸馏生成用例 + `runs/min_pass` 概率判定） |
| 想让 skill-up 驱动 DSH | 技术上可行（`engine.custom`，`transport: local\|http`，`response_format: session_result`），但 **custom 引擎不支持多轮 resume**，会退化成 batch —— 要用就得自己补一层 |

### 12.2 我们相对它们的差异（该保留的）

1. **oracle gate + canary**：两家都没有；我们的"判据自检 + 必挂断言"是防假绿的独有层；
2. **Wilson 区间**：两家都只有 mean / pass_rate，小样本假绿风险高；
3. **两臂默认都跑**：skill-up 的 `without_skill` 默认关闭，需要 `--baseline` 才跑；
4. **提问型 skill 的评测能力**：我们补了 `ask_user_question` 工具 + 脚本化 `userQuestions` 与**槽位答案银行**，两家都没有这一层（agentut 靠 mock，skill-up 靠 capture）；
5. **DSH 原生事件证据**（带 turn 号的 `tool/call`、`assistant/message.usage`、`turn/end.reason`）：不需要解析各家 CLI 的 stdout。

### 12.3 最值得抄的（按优先级）

1. **轮级 `post_condition` + `capture` + `{{var}}` 传值**（skill-up）：我们的断言是"够用"，但它把"上一轮产出喂给下一轮"做成了声明式，且**变量解析不到就在调 agent 之前 fail**；
2. **`expect` 免费闸 + 失败即跳过 judge + defaults 合并规则**（slice 追加去重 / scalar 覆盖）：省 token 且用例不重复；
3. **三态结果分类**：ERROR（基建/超时）、FAIL（断言）、SKIP（不适用）要分开——我们的报告目前只有 passed 布尔；
4. **`collect_artifacts` 失败也收集**（保留相对路径、排除 `.git/`）：出了问题时产物才是最需要的；
5. **agentut 的 `runs/min_pass` 三级覆盖 + 断言级通过率**：把"不确定性"变成显式指标，比布尔判定更接近真实；
6. **agentut 的 distiller→suggest**：从真实会话自动长回归用例，我们缺这条"真实流量→测试"的管道；
7. **给裁判的 fact-only 证据块**（禁指令 + 固定 JSON 契约 + 解析不到即 fail）；
8. **skill-up 的 `requested/applied/observed_configuration` 三态**：承认"我配了模型"≠"引擎真的用了这个模型"——我们的报告只记了 requested。


### 12.4 关键默认值与机制（原文数字，便于抄参数）

**skill-up**

- `cases.defaults`：`timeout_seconds: 300`、`max_turns: 12`、`parallelism: 1`（1–256）；`retry_policy{max_retries, retry_on: [timeout, error]}`；
- `cases.defaults.expect` 可做公共闸门，**合并规则：slice 字段（must_contain 等）追加去重且 defaults 在前；scalar 字段（exit_code、golden_file）被 case 覆盖**；
- `judge.agent_judge.pass_threshold` 默认 **0.7**；`context.limits.max_bytes` 默认 **65536**；`context` 可裁剪证据（final_message / transcript / workspace_diff: include|truncate|file_ref|omit / generated_files: index|include|omit）；
- `--iteration N`（N>1）写 `iteration-1..N` 做**抖动采样**；`--event-log` 输出 JSONL 事件流（末条 `last_event: true`）供 CI 实时 tail；支持 OTLP trace 导出；
- 结果三态：**PASS / FAIL（至少一条断言挂）/ ERROR（超时、引擎崩溃等基建问题）**；`grading.json` 是 Anthropic 兼容形状（只有 `expectations` + `summary`），完整状态在 `result.json` 的 `case_results[].grading`；
- 多轮支持的引擎机制：claude_code 用 `--resume <session-id>`、qodercli 用 `-r <session-id>`、codex 用 `codex resume <thread-id>`；**不支持 resume 的引擎只有在"无 post_condition / 无 capture / 无每轮规则"时才允许拼成单条 prompt 回退，否则判 ERROR**。

**agentut**

- `config.runs` 默认 **5**、`min_pass` 默认 **4（80%）**；优先级 **CLI > scenario > 全局 > 默认**；判定要求"场景 `passed_runs >= min_pass` **且每条断言自身** `passed_runs >= min_pass`"（断言可用自己的 `min_pass` 覆盖，如 `min_pass: 5`）；
- Matcher 优先级 **equals > contains > containsOneOf > regex > oneOf**（只有第一个字段生效）；字符串简写默认 equals，但 `response_contains` 默认 contains；
- mock 机制：`when` 数组是 **AND**，多条规则短路取第一条，无 `when` 则匹配该工具的全部调用；参数会被无害化（`file_path → .mock-empty`）并把原值存进 `metadata._agentutOriginalInput`，跑完再还原，否则会污染断言与蒸馏；
- 评分：有 `score.prompt` → 裁判返回 `{"score":n,"reason":"..."}`（clamp 0–100）；无 → **断言分** `round(通过断言数/总断言数×100)`，reason 固定 `"judge score by assertion"`；总分 `Σ(场景分×priority)/Σpriority`（priority 默认 10）；通过需"**所有断言过** 且 分数 ≥ `min_score`（默认 0）"；
- distiller：按 **user 消息切 step**；抽 `reasoning`（截断 200 字符）、`tool`（工具名/状态/入参/输出/错误）、`text`（最后一条非空）、**文件变更**（来自 `message.info.summary.diffs`，去重，缺省 modified）；给裁判的 `formatForJudge()` 明确"**只输出事实描述，不含任何指令**"；
- **没有 token / 成本指标**，只有次数、通过率、耗时。

### 12.5 一条战略建议

两家的产物格式都在向 **Anthropic skill-creator 的 `evals.json` / `grading.json` / `benchmark.json`** 收敛（skill-up 甚至能 `--auto` 直接吃 `evals.json`）。

→ 我们这套的下一个低成本高收益动作是：**把 `report.mjs` 的产物改成"同时输出我们自己字段 + Anthropic 兼容的 `grading.json`/`benchmark.json`"**。这样：
1. 用例和结果可以直接喂给 skill-up（评 Claude Code / codex）或别的生态工具；
2. 我们自己保留 oracle/canary/Wilson 这些增量能力；
3. 迁移成本从"重写用例"降为"改一个序列化器"。

## 13. 第二批调研（R5 · 2026-09-13）：skillgrade / 官方规范 / comet / skill-eval-harness

> 本批新打通的来源：`claude.com` 博客、`code.claude.com` 与 `docs.claude.com` 官方文档、`export.arxiv.org` 论文摘要页（此前不可达）；GitHub API 抓了 4 个新仓库共 24 份原文，存 `_web/files3/` 与 `_web/web/`。

### 13.1 mgechev/skillgrade（706★，TypeScript，"Unit tests for your agent skills"）

- **工作流**：`npm i -g skillgrade` → 在含 SKILL.md 的目录 `skillgrade init`（有 API key 时 AI 生成 tasks+graders）→ 手改 `eval.yaml` → `--smoke`(5 次)/`--reliable`(15)/`--regression`(30) → `preview`（本地 3847 端口看结果）。
- **agent 支持 6 类**：gemini/claude/codex（CLI）、acp（子进程 JSON-RPC over stdio，无需 API key）、opencode（`opencode run`，可指定 agent/model）、**command**（任意 CLI：instruction 写进 `/tmp/.prompt.md` 后 `cat | <command>`，**grader 评工作区状态，不评 stdout**）。
- **schema**（注意：顶层只有 `version`+`skill`；任务叫 `tasks`，夹具叫 `workspace`）：`defaults{agent,command,provider=docker,trials=5,timeout=300s,threshold=0.8,grader_model,grader_provider}`；`tasks[]{name,instruction,workspace[],graders[],agent,trials,timeout,expected?,metadata?}`；`workspace[]{src,dest,chmod}`；`graders[]{type=deterministic|llm_rubric,run|rubric,model,weight=1}`，总分 = `Σ(score×weight)/Σweight`。
- **grader 契约（很干净，值得抄）**：grader = 任意命令，stdout 上**只允许一段 JSON**：`{score:0..1, details:string, checks[]?:{name,passed,message}}`；调试输出必须走 stderr；**退出码 0 = grader 跑成功（score 0.0 也算），非 0 = grader 本身坏了**。输入通道：deterministic 从环境变量 `SKILLGRADE_INPUT` 拿 `{task,trial,expected,metadata}`，**agent 退出后才注入、不落工作区**（答案键防泄漏）；llm_rubric 把 `expected` 渲染进 prompt。
- **组织能力**：`$import`（文件/目录/glob/列表，可嵌套、成环报错）+ `--filter=tier=easy,medium`（同 key OR、跨 key AND；filter 未声明的 key 报错而非匹配全部）。
- **它没有的**：对照组（无 without_skill/old_skill 臂）、统计口径（只有 pass rate + `--threshold=0.8` 硬门，无区间）、oracle/canary（`--validate` 靠作者自写 `solution`）。作者自己的建议：**grade outcomes not steps；3–5 个好任务胜过 50 个噪声任务**。

### 13.2 agentskills 官方规范站（第一方权威口径）

- **evaluating-skills.mdx**：手工只写 `evals/evals.json`（`{skill_name, evals:[{id,prompt,expected_output,files[],assertions[]}]}`，2–3 条起步）；目录约定 `<skill>-workspace/iteration-N/<eval-name>/{with_skill,without_skill}/{outputs/,timing.json,grading.json}` + `benchmark.json`；**每轮跑两遍（with vs without；改版用 `cp -r` 快照做 old_skill 基线）**；判分逐断言 PASS/FAIL 且**必须给具体证据**；"标签在但内容空 = FAIL"；**官方明确把"两边都过/都挂/只 with 过/波动大"作为四类分析动作**。
- **optimizing-descriptions.mdx（触发率官方流程）**：`eval_queries.json` 约 20 条（8–10 正、8–10 负且必须 near-miss）；**每条跑 3 次**算 trigger rate，阈值 **0.5**；**train ~60% / validation ~40% 随机打乱后固定划分**，只用 train 失败驱动修改、**按 validation pass rate 选版**（最优不一定是最后一版）；约 5 轮；禁止把失败 query 的关键词塞进 description（过拟合）；改完用 5–10 条全新 query 终检。
- **specification.mdx（我们 L0 的依据）**：`name` 1–64 字符、仅 `a-z0-9-`、不以 - 开头/结尾、无连续 --、**必须等于父目录名**；`description` 1–1024 字符且同时说明"做什么+何时用"；可选 `license`/`compatibility`(≤500)/`metadata`/`allowed-tools`；**正文推荐 <5000 tokens、硬性 500 行以内**；引用只一层深；官方校验器 `skills-ref validate`。
- **best-practices.mdx**：每段自问 "Would the agent get this wrong without this instruction?"，否则删；"不用 skill 也能做好 → skill 可能没价值"；gotchas 被纠正一次就补一条；**跨用例看 trace，每次重造同一脚本就 bundle 进 `scripts/`**。

### 13.3 rpamis/comet（3024★）：一个产品怎么给自己做评测

- `comet eval <target>`：target 是 eval.yaml 或 SKILL.md；suite=local|langsmith|langfuse；底层是 pytest 任务文件；judge 由 manifest/参数/`BENCH_LLM_JUDGE` 开启；产出实验号 `comet-eval-<uuid>` + `runs/<id>/summary.md|html`，local 跑完**回写仓库实验记录**。
- **CI（eval-regression.yml）的原则**：真实模型评测**只手动触发**（workflow_dispatch，"consume paid API capacity"）；`concurrency` 不取消进行中的跑；timeout 60min；日志 **`if: always()` 上传**；门禁是参数化的 `regression_check.py --count 1 --tolerance 0.10`（而非全绿）。
- **他们给自己立的规则（60-eval.md）**：静态校验、Docker 场景、真实模型 Eval **分别报告，不得以收集成功替代真实运行**；归因分 **harness/workflow/task/model** 四类，环境噪声可标记，**真实低分不得过滤**；token 只经环境变量，不写入任何文件。
- **公开的真实报告（benchmark-report.json）**：beta16 vs beta17，`usable_waves=[B,C,D,F]`、`excluded_waves=[E]`（`reason: API rate limit or quota failure`，且 turns/tokens/cost 置 null——**排除要留痕，不静默丢样本**）；54/73=74.0%·52.1min·$25.13 vs 58/65=89.2%·42.4min·$21.08；**跨协议版本对比时明示 caveat**。
- **README 公布的对照结论**（16 任务、每处理 48 runs、41 个双方皆过的配对样本）：tokens **-76.8%**、轮次 **-57.4%**、时间 **-47.4%**；pass^3 87.5%(+12.5pp)、pass@3 两版均 100%。**注意他们区分 pass@k（至少一次过）与 pass^k（全部过）**。

### 13.4 adewale/skill-eval-harness（74★，Python）＋ 官方网页 / SkillsBench 论文摘要

**这是目前见到的方法论最严谨的一套**（文档按问题组织：did-my-edit-regress / worth-its-tokens / can-i-trust-my-judge / …）：

- **只测因果 lift**：数字只能来自同一 `(case_id, model, run_number, population)` 下的 with−without 差；`without_skill` 工作区**物理上不含 skill 文件**；缺臂 blocked、重臂 invalid。
- **回归的定义**：**带 provenance 的"指名断言"由 pass 翻 fail**，不是目测 diff。显著性用 per-case-model **paired sign-flip**（双侧），**≥6 对才可能 p≤0.05**（2/2⁶=0.03125），不足报 INDETERMINATE 而不是硬给结论。
- **消融臂**：从 skill 文件本身物化出"删掉某一段"的变体（frontmatter 字段 / section（fence-aware）/ list_item / 删除式 patch / reference / script），五道硬门（净删除、两两不相交、layer cohesion、必填字段保留、路径 containment），物化臂对 judge **blind**，附 `skill_hash` 与 `removed_bytes`。
- **judge 三段校准（都不在判分路径上）**：①robustness（order-flip 一致性 + 两个必拒负控：空输出、master-key 注入 → `control_leak_rate`）→ ②alignment（人工标签对齐到 `case::variant::run-n::assertion`，出 agreement/**Cohen's kappa**/precision/recall；实测"高一致率 + kappa≈0 = 只是跟着标签基率走"；`--min-labels 50`）→ ③compare-judges（`lift_by_judge`、`magnitude_spread`、sign/magnitude_sensitive，`--magnitude-eps 0.1`）。
- **token 性价比**：口径 = **每 1k 额外 token 的客观 lift** 与 lift-per-dollar；缺遥测记 `source:"missing"`，**缺失≠零**；执行错误计成本但不入 lift 分母；`saturated`（用例太简单）与 `no-lift`（skill 没用）分开报。
- **触发与答案两个 population 永不混加**；触发矩阵按 `(agent, model, query)` 跑，**`--runs-per-query 3` 是下限**（他们实测 3 个单次结论在 n=5 时 2 个被推翻）；检测靠 skill 挂载或 `Skill` 工具调用，**不靠回答里出现 skill 名字**。
- **"evals are not tests"**：test 判"对不对"，eval 判"改动移动了多少"；两臂全绿是**警告**；一次运行是采样；"能永远通过的 test 是完成了，**能永远通过的 eval 是坏了**"。CI 两道独立门（离线）：report 的 junit/github + `audit-manifest --fail-on-blockers`；**硬门**＝被确认的命名回归（≥6 对、p≤0.05）与 readiness blockers；**不门**＝without_skill 的失败（预期）、errors>0（先重跑）、soft 轻微下滑。

**官方网页四份**：

- **Anthropic 博客（2026-03-03）**：skill 分 **capability uplift** 与 **encoded preference** 两类，测试理由不同；benchmark 追 pass rate / elapsed / tokens；comparator 做盲 A/B；6 个公开文档 skill 的描述调优 **5/6 触发改善**。
- **Claude Code 官方文档（重要，改变格局）**：**Claude Code 已内置 `claude plugin eval`**——每条 prompt 在隔离 session 里**带/不带 plugin 各跑一次**、grader 可自写或代写、**低于阈值非零退出（可直接 gate CI）**、产物就是 `grading.json`/`benchmark.json`、另有盲 A/B 版本比较、description 调优、HTML review viewer、`tool_used: Skill` 型 grader 测触发；`claude plugin validate .claude/skills` 需 **v2.1.233+**（本机 2.1.170 尚无）。**预算数字**：description 列表预算 = 模型上下文的 **1%**；单条 description + when_to_use 上限 **1,536 字符**；自动压缩保留每 skill 前 **5,000 tokens** + 共享 **25,000 tokens**。
- docs.claude.com 的 agent-skills 概览页是**区域封锁页**（正文只有 "App unavailable in region"），无内容可引——数据缺口。
- **SkillsBench 论文摘要（arXiv:2602.12670v4，77 位作者）**：87 任务、8 领域、deterministic verifiers、18 个 model-harness 配置；matched 对照下平均 **33.9% → 50.5%（+16.6pp，归一化 +25.5%）**，配置级增益 **+4.1 ～ +25.7pp**；**至多三个模块的 focused skills 优于更大或穷尽的 bundle**；**小模型 + Skills 可追平不带 Skills 的大模型**；结论：**paired evaluation 是严谨衡量 skill 效力的基础**。

### 13.5 本批结论：格局变化与我们该抄什么

**格局变化**：`claude plugin eval` 官方内置后，"两臂 + graders + 阈值退出码 + grading/benchmark 产物"这层已经**不需要自研**（本机 2.1.170 还没有，升级即得）。**我们 cc-eval 的差异化价值收窄为**：按轮多轮断言、oracle/canary、Wilson 区间、槽位脚本用户（提问型 skill）、以及"判据与统计独立于任何厂商 CLI"。

**最值得抄（按优先级，前五条来自 skill-eval-harness）**：

1. **配对实验身份**：lift 只能来自 `(case, model, run, population)` 封闭对；without 工作区物理不含 skill（我们已做到文件层面，但没把"对"建成一等公民）；
2. **回归 = 指名断言翻转 + 显著性门（≥6 对 paired sign-flip，p≤0.05），不足报 INDETERMINATE**——这直接回答了"我改了 skill 会得到什么"的严谨版；
3. **消融臂**：从 SKILL.md 物化"删一段"的变体当模拟回归（我们连 old_skill 快照臂都还没有）；
4. **judge 三段校准**（robustness 负控 / alignment kappa≥50 标签 / compare-judges），且 judge 花费单列、judge ≠ 被测模型；
5. **token 性价比口径**：lift per 1k extra tokens、lift per \$，缺遥测记 missing 不记 0。

**次优先（来自本批其它来源）**：skillgrade 的 grader 契约（stdout 单 JSON + exit 0=跑成功）与 `SKILLGRADE_INPUT` 后注入；comet 的排除留痕（`included/reason` + null）与"真实低分不得过滤、归因四分类"；官方触发流程（20 条×3 次、0.5 阈值、60/40 固定划分、按 validation 选版）；官方预算数字进 L0（description+when_to_use ≤1,536 字符、目录预算=上下文 1%）。

## 14. 建议的下一步（需你确认）

1. 先做 M0（转录解析 + 断言），把本次实测的两个探针固化成回归用例；
2. 把 `skill-test-kit` 的探针资产迁到 DSH 口径，跑一轮"存量 skill 基线"；
3. 决定 L2 是否纳入：若纳入，需要先定义每个 skill 的"可机检产物"（否则只能靠 LLM 裁判）。

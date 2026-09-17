# CHANGELOG（总账）

> **公开版说明**：本仓库为公开版本，**不包含内部样本库的 skill 用例与夹具**（fe-req-analysis / fe-dev-design / fe-dev-chain / fe-test-design 四个用例及其夹具仅存在于私有版本）；下文提及这些名字处均为过程记录，不含样本本体。
> **位置**：本文件是本项目群（调研 + 两个引擎的评测能力 + 文档）**所有改动的总账**。
> **约定（方案 B）**：每一步改动**都必须在这份总账里留一条**；实现级细节可以留在各项目分账里，总账条目给出"详情位置"。
> **每条必须包含**：编号 / 日期 / 项目 / 改了什么 / 为什么 / 证据（命令 + 观测到的数字或输出）/ 影响文件 / 怎么回退 / 详情位置。
> **只追加、不修改**；写错了就再追加一条更正条目。
> **不改代码只跑评测也要记**（记通过率、耗时、花费）。

分账（细节）：

| 分账 | 覆盖范围 |
|---|---|
| `cc-eval/CHANGELOG.md` | Claude Code 引擎版的实现级细节（C1–C13 的完整版） |
| `skill-eval/MANUAL.md` §7/§11、`README.md` | DSH 引擎版的机制、来源与限制 |
| `skill-eval-research.md` | 调研结论：§9 最佳实践、§11 DSH 版实现、§12 同类工具对照 |

---

## 索引

| 编号 | 日期 | 项目 | 变更摘要 | 详情 |
|---|---|---|---|---|
| P6 | 2026-09-12 | 流程 | 记录制度改为**总账（方案 B）** | 本文件 §流程约定 |
| D4 | 2026-09-12 | 文档 | 新增本总账 | 本文件 |
| CC1–CC13 | 2026-09-12 | cc-eval | Claude Code 评测 CLI 从 0 到跑通全量 | `cc-eval/CHANGELOG.md` |
| **CC14** | 2026-09-12 | cc-eval | **3 次重复跑出真统计**（每臂 3/3 vs 0/3，macro lift=1，$1.45） | 本文件 §CC14 |
| **CC15** | 2026-09-13 | 跨引擎 | **统一产物格式**：共享 `shared/anthropic-artifacts.mjs`，两引擎输出同一套 `grading.json`/`benchmark.json`；canary 剔除出聚合 | 本文件 §CC15 |
| **CC16** | 2026-09-13 | cc-eval | **run 级并发**（`--concurrency`）：全量 8 分钟 → **166s（≈2.9×）**，成本不变；修一个漏 `await` 的假失败 bug | 本文件 §CC16 |
| **R5** | 2026-09-13 | 调研 | 第二批：skillgrade/官方规范/comet/skill-eval-harness + 官方文档与 SkillsBench 摘要；**发现官方已内置 `claude plugin eval`** | 本文件 §R5 |
| **CC17** | 2026-09-13 | cc-eval | **用 6 个真实 skill 广度验证**：4 项 harness 扩展（glob 断言/按轮 oracle/案例级断言/夹具白名单）+ 修"重跑不封闭"bug + 1 个真发现（fe-dev-design 边界违规） | 本文件 §CC17 |
| D3 | 2026-09-12 | 文档 | `cc-eval/SPEC.md` + `README.md` + `CHANGELOG.md` | `cc-eval/` |
| R4 | 2026-09-12 | 调研 | 同类工具拆解：alibaba/skill-up、agentut | `skill-eval-research.md` §12 |
| S1–S10 | 2026-09-12 | skill-eval | DSH 多轮评测 harness 从 0 到 3 次重复统计 | `skill-eval/MANUAL.md` |
| R1–R3 | 2026-09-12 | 调研 | 本机资产 + DSH 源码 + 38 份外部最佳实践原文 | `skill-eval-research.md` §1–§9 |
| P1–P5 | 2026-09-12 | 口径 | 统计口径、两臂默认、防自欺、退出码、文档同步 | 本文件 §口径 |

---

## 流程约定（P6 · 2026-09-12）

- **改了什么**：记录制度从"按项目各自记"改为"**一份总账**"（本文件），实现细节保留在各项目分账。
- **为什么**：跨项目的口径/决策变更（例如"统计从 Wald 改为并报 Wilson"、"退出码只对 skill 臂负责"）分散在多份文件里会漂移；总账让"什么时候因为什么改了什么"一眼可查。
- **证据**：本文件与 `cc-eval/CHANGELOG.md` 并存，索引表列出全部条目。
- **影响文件**：`CHANGELOG.md`（新增）、`cc-eval/CHANGELOG.md`（保留为分账）。
- **回退**：删除本文件，回到项目分账。
- **执行要求**：后续每次改动 → 先在总账追加条目（编号、五要素齐全），再在分账里补实现细节；回复用户时同步说明。

---

## 口径与约定（P1–P5 · 2026-09-12）

| 编号 | 约定 | 为什么 | 落地位置 |
|---|---|---|---|
| P1 | 指标口径沿用 skilljack/SkillsBench：`resolutionRate` / `pass@k` / `lift` / `macroLift` / `skillInvocationRate`；**额外并报 Wilson 区间** | 口径统一才能跨工具比较；Wald 在 p=0/1 时退化（实测 3/3 → `[1,1]`），Wilson 才诚实 | `cc-eval/lib/stats.mjs`、`skill-eval/report.mjs` |
| P2 | **两臂默认都跑**（`with_skill` + `without_skill`） | 没有基线就没有 lift；"skill 有没有用"必须与无 skill 对照 | `cc-eval/cc-eval.mjs`、`skill-eval/run.mjs` |
| P3 | **防自欺三件套**：oracle gate（判据可达）+ canary（判据会失败）+ 夹具卫生（产物不得预先存在） | 历史事故：夹具残留产物让两臂都假 PASS、lift=0；判据写错会静默恒真 | `cc-eval oracle`、`cases/canary-*.json`、`skill-eval/oracle.mjs` |
| P4 | **退出码只对"skill 臂是否达标"负责**（外加 canary 必须挂） | 基线失败是 lift 的来源、是预期结果；把它当失败会让 CI 永远红 | `cc-eval/cc-eval.mjs` 的 verdict 段 |
| P5 | **文档与代码同步**：行为变了就同时改 `SPEC.md`/`MANUAL.md` 对应章节 | 防止文档漂移 | 各项目文档 |

---

## 调研阶段（R1–R4 · 2026-09-12）

### R1 · 盘点本机已有资产
- **证据**：`D:\work\skill-test-kit`（Claude Code 版 L0+L1，实测 3 skill×15 探针 14/15、6 skill×26 探针 23/26、14 条坑清单）；`D:\work\deepseek-harness-master`（DSH 源码仓）。
- **影响**：证明了"两臂 + 探针 + 修复环"这条路在 Claude Code 上已被验证过。

### R2 · DSH 源码与文档调研
- **证据**：`ctx.skills` 注册表、`SKILL.md` frontmatter 规则与发现根 rank、catalog 注入模板、`skill` 工具返回结构、`agent.followup()/whenIdle()`、会话事件类型、`--patch` overlay 语义。
- **详情**：`skill-eval-research.md` §2、§3。

### R3 · 外部最佳实践（读原文，不是标题）
- **改了什么**：用 `api.github.com` 抓取 38 份原文并逐字阅读。
- **证据**：anthropics/skills 的 skill-creator（两臂同批跑、`evals.json`/`grading.json`/`benchmark.json` 形状、描述优化 20 条/60-40/3 次/≤5 轮按 test 分选）、skilljack-evals（指标公式、oracle gate）、SkillsBench（Oracle must pass before agent runs、测试设计规范）、crashcart（21 项静态检查、描述"pushy 且 sharp"）、rhyanvargas（canary、fails-closed）、addyosmani、groundwork、rsc、hesham。
- **限制**：`raw.githubusercontent.com` 与 HuggingFace 不可达；OpenAI 那篇博客 403——**未采信任何论文数字**。
- **详情**：`skill-eval-research.md` §9（含来源链接）。

### R4 · 同类工具拆解
- **证据**：alibaba/skill-up（Go，888★）：`expect` 零成本闸门 + `judge` 三层、`input.turns` 真会话 resume + `post_condition`/`capture`/`{{var}}` + 轮级断言、`--baseline` 两臂、Anthropic 兼容产物、GitHub Action；agentut（TypeScript，opencode）：只记录输入不记录响应、7 种断言 + Matcher、`runs/min_pass`（默认 5/4）概率判定、session 蒸馏生成用例、fact-only 裁判摘要、mock 注入。
- **结论**：目标引擎是 Claude Code/codex 时应直接用 skill-up；opencode 用 agentut；**自研的增量价值是 oracle/canary、Wilson 区间、两臂默认、提问型 skill 的评测**。
- **详情**：`skill-eval-research.md` §12（含 §12.4 默认值、§12.5 战略建议：产物同时输出 Anthropic 兼容格式）。

---

## DSH 引擎版 `skill-eval`（S1–S10 · 2026-09-12）

> 详情见 `skill-eval/MANUAL.md`；产物在 `D:\Games\robot\skill-eval\`。

| 编号 | 改了什么 | 为什么 / 证据 |
|---|---|---|
| S1 | **可行性验证**（无代码）：正例/负例/崩溃三次真跑 | headless 只跑单轮且**未挂 `ask_user_question` 工具**（模型原话"当前会话中没有该工具"）；正例加载 skill 成功；负例零 skill 调用；**杀掉进程后转录仍有 30 条事件** → 证据不依赖正常退出 |
| S2 | **多帧 zstd 解码** | 整文件 `zstdDecompressSync` 只解首帧（实测只得 168B）；改逐帧解出 9 帧 / 40 事件 |
| S3 | **插件替换一次性 runner** | `overlay.yml` 禁用 `headless-runner`/`headless-startup` 并 `insert` 自己的 runner；踩坑：新条目必须放 `insert:`，否则报 `entry not found` 且进程静默挂死 |
| S4 | **多轮驱动 + 提问链路** | `agent.followup()` + `await whenIdle()` 逐轮驱动；挂 `dsh-tool-ask-user` + 脚本化 `userQuestions` provider；`user_questions: scripted\|unavailable` 两模式；槽位答案银行（按关键词匹配"问的问题"，抗轮次漂移） |
| S5 | **夹具污染事故 → 卫生检查** | 残留 `plan.md` 让两臂都假 PASS、lift=0；改为用例声明 `artifacts`，脏了直接报错退出 |
| S6 | **两臂批量 + 报告** | `run.mjs`（每 case × 臂 × 重复，独立工作区）/ `report.mjs`（率、区间、lift、成本、时长） |
| S7 | **3 次重复 + 统计** | 15 次运行、204k token：`with_skill` 3/3、`without` 0/3、macro lift=1；**发现 Wald 在 3/3 时退化成 `[1,1]`，补报 Wilson `[0.438,1]`** |
| S8 | **oracle gate + canary** | `oracle.mjs` 正向控制（合成产物必须能过）+ 负向控制（canary 必挂）；canary 挂了则报告标 `BROKEN` |
| S9 | **参数解析 bug** | `--repeats 3` 的 `3` 被当成 case id（`cases\3.json` ENOENT）；改为"裸 token 若不是某个 `--flag` 的值才算 case id" |
| S10 | **文档** | `README.md`（怎么跑）、`MANUAL.md`（原理/结果/回归/移植，含 §11 来源清单） |

---

## Claude Code 引擎版 `cc-eval`（CC1–CC13 · 2026-09-12）

> 完整记录（含每一步的命令、数字、回退方式）见 **`cc-eval/CHANGELOG.md`**。摘要：

| 编号 | 摘要 |
|---|---|
| CC1 | 可行性：`claude -p --output-format json` 无人值守可用（`session_id`/`cost`/`modelUsage` 齐全） |
| CC2 | skill 生效可确定性观测：`Skill {"skill":"ping-check"}` → `tool_result: "Launching skill: ping-check"` |
| CC3 | cc-eval 骨架：`cc-eval.mjs` + `lib/assert.mjs` + `lib/stats.mjs`；**每轮一进程 + `--resume` 同会话 + stdout 走文件 fd 不走管道** |
| CC4 | 三用例 + 夹具（`ping-skill` / `clarify-multiturn` / `canary-never`） |
| CC5 | oracle gate 三条全 OK |
| CC6 | 首次真跑 `ping-skill`：with PASS(6.8s) / without FAIL(35.3s) |
| CC7 | **判据过宽 bug**：`must_not_ask` 用"有问号"判定 → 礼貌问句被误判；拆成宽松 `must_ask_user` / 严格 `must_not_ask`（只认工具）+ 子句级 `must_not_reask` |
| CC8 | **正则恒真 bug**：`/[?？]/.test(s + '?')` 恒真；改 `text.match(/[^。！!？?\n]*[？?]/g)` |
| CC9 | 第三次跑通过：`[Skill,AskUserQuestion]` → `[Write,Read]`，27.5s，$0.113；**附带发现 `AskUserQuestion` 在 `-p` 下只回占位 `"Answer questions?"`** |
| CC10 | 退出码语义修正：只对 skill 臂 + canary 负责 |
| CC11 | `armStats` 字段修正（`numTurns` → `turnsUsed`） |
| CC12 | 全量跑（3 用例 × 2 臂）：macro lift=1、canary=ok、合计 **$0.5193**、约 2.5 分钟 |
| CC13 | 文档：`SPEC.md` + `README.md` + `CHANGELOG.md` |

---

### CC14 · 2026-09-12 · 3 次重复跑出真统计（P0）

- **改了什么**：没有改代码；把评测从"每臂 1 次"提升为 **`--repeats 3`**，15 次真实调用（3 用例 × 2 臂 × 3 次，canary 只跑 1 臂 × 3）。
- **为什么**：n=1 时 Wilson 区间是 `[0.207,1]`，几乎没有信息量；Wald 在 p=0/1 还会退化，必须用重复把"稳定率"做出来。
- **证据**（`node cc-eval.mjs run --repeats 3` → `report`，退出码 0）：
  ```
  ping-skill        with_skill  3/3 rate=1 wilson=[0.438,1] pass@k=true turns=1 wall= 6.4s $0.0631
                    without     0/3 rate=0 wilson=[0,0.562] pass@k=false turns=1 wall=26.0s $0.1022  lift=1
  clarify-multiturn with_skill  3/3 rate=1 wilson=[0.438,1] pass@k=true turns=2 wall=40.5s $0.1309
                    without     0/3 rate=0 wilson=[0,0.562] pass@k=false turns=2 wall=49.0s $0.1652  lift=1
  canary-never      with_skill  0/3（应当失败）            canary=ok
  macro lift = 1 | 合计成本 = $1.4499 | 约 8 分钟
  ```
- **本轮新观测（值得单独记）**：
  1. **通过率很稳、时间很不稳**：`clarify-multiturn/with_skill` 三次分别 59.6s / 37.3s / 24.7s（**2.4 倍差距**），而三次断言全过 → **报告必须同时给率、时长、成本三列**，只看时长会得出"skill 让任务变慢"的错误印象；
  2. **技能臂更省钱也不稳定**：`ping-skill` 本轮技能臂 $0.0631 < 基线臂 $0.1022（上一轮单次跑是 $0.1229 > $0.0935）→ 单次成本对比**不可作为结论**；
  3. **工具轨迹高度一致**：技能臂三次都是第 1 轮 `Skill`（+ `AskUserQuestion`）；基线臂三次都是 `Bash/Glob` 在空工作区里乱找；
  4. 技能臂第 2 轮出现 `[Write,Glob,Glob]` 仍判 PASS —— 断言容忍"只读的额外探索"，这符合设计意图。
- **影响文件**：`cc-eval/out/runs/*`（15 份 report.json + grading.json + 原始 jsonl）、`out/summary.json`、`out/benchmark.json`（本次运行产物，未改代码）。
- **回退**：删除本轮 `out/` 产物即可；代码未变。

### CC15 · 2026-09-13 · 统一产物格式：两个引擎输出同一套 Anthropic 兼容产物

- **改了什么**：
  1. 新增共享模块 **`shared/anthropic-artifacts.mjs`**（唯一实现）：`gradingFromRun(run)` 与 `benchmarkFromCases(cases, meta)`；
  2. `cc-eval/lib/stats.mjs` 改为复用它（保留 `armStats`/`wald`/`wilson`），`cc-eval.mjs` 的 `benchmark.json` 改由新 API 生成；
  3. `skill-eval/report.mjs` 新增：每次运行写 `out/grading/<case>.<arm>.<run>.grading.json`，聚合写 `out/benchmark.json`；
  4. **canary 用例从 `run_summary` 聚合中剔除**（只在 `cases[]` 里逐条展示），并在 `metadata.canary_cases_excluded` 里记数。
- **为什么**：
  - 两个引擎必须产出**同一形状**的 `grading.json`/`benchmark.json`，否则结果不可比、也无法喂给生态工具（skill-up 的 `--auto` 直接吃 Anthropic `evals.json`，其产物也是这套形状）；
  - 修正一个真实缺陷：canary 的断言**按设计必须失败**，把它算进平均会把 `with_skill.pass_rate.mean` 从 1.0 拉到 **0.667**，让健康的运行看起来像坏了。
- **证据**（两个引擎各自重新聚合，**未重跑 LLM**）：
  ```
  DSH (skill-eval)   with_skill pass_rate=1  time= 9.1s  tokens=10585
                     without    pass_rate=0  time=51.4s  tokens=19146   delta: +1 / -42.3s / -8561
  Claude Code (cc-eval) with_skill pass_rate=1  time=23.5s  tokens= 7179
                     without    pass_rate=0  time=37.5s  tokens= 8799   delta: +1 / -14.0s / -1620
  ```
  两个文件的 `run_summary` 结构一致（`{pass_rate,time_seconds,tokens:{mean}}` + `delta`）；`metadata` 记录 `engine`/`cases`/`canary_cases_excluded`/`runs_per_configuration`。
- **影响文件**：`shared/anthropic-artifacts.mjs`（新增）、`cc-eval/lib/stats.mjs`、`cc-eval/cc-eval.mjs`、`skill-eval/report.mjs`、`cc-eval/SPEC.md`、`skill-eval/MANUAL.md`。
- **回退**：恢复 `cc-eval/lib/stats.mjs` 内的本地实现、去掉 `skill-eval/report.mjs` 的两处写入、删除 `shared/`。

### CC16 · 2026-09-13 · run 级并发（`--concurrency`），全量 8 分钟 → 166 秒

- **改了什么**：
  1. `cc-eval.mjs`：`runTurn` 由 `spawnSync` 改为 **async `spawn`**（stdio 仍走文件 fd，不走管道），并加 `killTree()`（Windows 用 `taskkill /T /F`，因为 `child.kill()` 杀不掉 agent 拉起的子进程树）与手动超时；
  2. `cmdRun` 重构为"任务列表 + 工作池"：**并发粒度 = run（case × arm × repeat）**，每个 run 内的轮次仍然串行（共用一个 `--resume` 会话）；每个 run 本就有独立工作区副本，天然无文件冲突；
  3. 新增 `--concurrency N`（默认 1，保持旧行为）；判定逻辑抽成 `verdictOf(results)`，语义不变。
- **为什么**：反馈回路太长（全量 3 次重复串行约 8 分钟），瓶颈是 `without_skill` 臂（22.9–68.8s/次）；run 级并发不改任何判据语义，风险最低。
- **过程中发现并修复的 bug（记入教训）**：`runTurn` 改成 Promise 后调用点漏了 `await`，导致 `r.wallMs` 为 undefined → 报告里 `wallMs: null`（`JSON.stringify(NaN)` 的结果）、`existsSync(Promise)` 触发 Node 弃用告警、`normalizeTurn(undefined)` 读不到事件 → 全部运行假失败。一行修复（`await runTurn`）。
  **教训**：把同步函数异步化时，调用点的 `await` 必须同一批改；症状（报告字段 null + 弃用告警）比报错更隐蔽。
- **证据**：
  - 冒烟（3 任务，`--concurrency 3`）：ping/with PASS 5.6s、canary FAIL（应当）9.3s、ping/without FAIL 28.4s，总墙钟 **28s ≈ 最长任务**而非串行之和 43s；`EXIT=0`；`existsSync` 告警消失。
  - 全量（15 任务 = 3 用例 × 2 臂 × 3 次，`--repeats 3 --concurrency 3`）：**墙钟 166s（约 2.8 分钟）**，对比 CC14 串行约 8 分钟（当时未精确计时，任务在一个 600s 等待窗内完成）→ **≈2.9× 提速**；成本 $1.4151（CC14 为 $1.4499，同工作量）；结论完全一致：with_skill 3/3、without 0/3、canary ok、macro lift=1、`EXIT=0`。
  - 并发下的新观测：`clarify-multiturn/without_skill#3` 第 2 轮出现 `[Bash,Write×2,TaskCreate×5,TaskUpdate×2]`、96s、$0.3196 —— **基线臂的行为漂移很大**（这次它开始建任务清单），进一步佐证"基线不仅慢且不可预测"。
- **影响文件**：`cc-eval/cc-eval.mjs`；文档同步 `SPEC.md`、`README.md`。
- **回退**：`--concurrency 1` 即回到串行路径；代码回退需恢复 `runTurn` 的 `spawnSync` 版本与 `cmdRun` 的三重循环。

### R5 · 2026-09-13 · 第二批调研：skillgrade / agentskills 官方规范 / comet / skill-eval-harness ＋ 官方文档与论文摘要

- **改了什么**：无代码改动；新打通 4 条来源（`claude.com`、`code.claude.com`、`docs.claude.com`、`export.arxiv.org`），GitHub API 抓 4 个仓库 24 份原文（`_web/files3/`）+ 4 份网页正文（`_web/web/`），三路子代理逐字精读。
- **产出**：`skill-eval-research.md` 新增 §13（13.1 skillgrade、13.2 agentskills 官方规范、13.3 comet、13.4 skill-eval-harness+官方网页+SkillsBench 摘要、13.5 结论）。
- **关键发现（改变决策的三条）**：
  1. **Claude Code 已内置 `claude plugin eval`**（两臂 + graders + 阈值退出码 + grading/benchmark 产物 + 盲 A/B + 描述调优；`validate` 需 v2.1.233+，本机 2.1.170 尚无）→ 自研的差异化收窄为：按轮多轮断言、oracle/canary、Wilson、槽位脚本用户、厂商无关；
  2. **SkillsBench 论文数字到手**：87 任务/8 领域/18 配置，33.9%→50.5%（+16.6pp，归一化 +25.5%）；≤3 个 focused 模块优于大 bundle；小模型+Skills ≈ 大模型；**paired evaluation 是基础**；
  3. **skill-eval-harness 给出了我们缺的三块的完整答案**：回归判定（指名断言翻转 + ≥6 对 paired sign-flip p≤0.05，不足 INDETERMINATE）、消融臂（从 SKILL.md 物化删段变体 + 五道硬门）、judge 三段校准（负控/kappa≥50 标签/compare-judges）。
- **其它要点**：官方预算数字（description+when_to_use ≤**1,536 字符**、目录预算=上下文 **1%**、压缩保留每 skill 前 5,000 tokens）；官方触发流程（20 条×3 次、0.5 阈值、60/40 固定划分、按 validation 选版）；skillgrade 的 grader 契约（stdout 单 JSON、exit 0=跑成功）与 `SKILLGRADE_INPUT` 后注入；comet 的排除留痕与归因四分类（harness/workflow/task/model）；"evals are not tests"（两臂全绿是警告；能永远通过的 eval 是坏了）。
- **数据缺口**：`docs.claude.com` agent-skills 概览页为区域封锁页，无正文。
- **影响文件**：`skill-eval-research.md`（新增 §13）、本文件。
- **回退**：删除 §13 即可。

### CC17 · 2026-09-13 · 用 6 个真实 skill 做广度验证（含 4 项 harness 扩展、2 个 bug 修复、1 个真发现）

- **改了什么**：
  1. **新增 6 个真实 skill 用例**（skill 来源：本机 `skill-test-kit` 的 6 个样本，3 个为 anthropics 官方 skill）：`fe-req-analysis`（需求分析→文档）、`fe-dev-design`（技术方案→文档）、`fe-dev-chain`（无需求时的边界/链路行为，2 轮）、`fe-test-design`（测试设计→文档）、`frontend-design`（纯文本建议型，无产物）、`webart`（执行型，要跑 init/bundle 脚本）；
  2. **断言库扩展**（真实 skill 逼出来的）：`must_write_file_pattern` / `must_not_write_file_pattern`（glob 产物断言，真实 skill 的产出文件名带变量且**位置自选**——实测模型把产物写到 `docs/` 子目录）；案例级断言 `must_call_skill_any_turn`（**skill 会话内只加载一次**，第 2 轮不会再调 Skill 工具）；
  3. **oracle 改为按轮累积物化**（`turn.oracle`）：多轮用例里正负极性断言需要"当轮应有的世界状态"，案例级 oracle 是最终状态、会污染第 1 轮的 must_not 判定；
  4. **夹具白名单守卫**（`fixture_allowlist: ['.claude']`）：边界用例要求工作区几乎为空，残留输入文件会把用例变成另一个实验；
  5. **修复 2 个 harness bug**：① `prepareWorkspace` 用 `cpSync` 覆盖拷贝但**不清空目标**→ **重跑不封闭**（上一轮产物残留、满足/触发本轮断言；本次差点把"夹具残留"误判成"skill 越界"，靠第 1 轮回复里"这份方案在我接手前就已存在"一句定位）；② `assert.mjs` 未转发导出 `findFilesByPattern`；
  6. `webart` 超时 600s → **1200s**（实测 600s 内 init+开发+bundle 未完成，两臂同时超时，`cost=$0` 因 result 事件未到达）。
- **为什么**：此前只有 2 个玩具 skill，"harness 是否通用"与统计意义都不足。
- **证据**（广度轮聚合，轻用例各 1 次、ping/clarify/canary 3 次）：
  ```
  ping-skill / clarify-multiturn   with 3/3 PASS，without 0/3     lift=1
  fe-req-analysis / fe-dev-design / fe-test-design / frontend-design
                                   with 1/1 PASS，without 0/1     lift=1
  webart（执行型）                 with 断言过但 600s 超时（aborted），needs 1200s
  fe-dev-chain（边界用例）         with 0/1 且 without 0/1        lift=0
  macro lift = 0.875 | canary ok | 本轮累计 $4.83
  ```
- **真发现（n=1，待重复验证）**：`fe-dev-design` 的 SKILL.md 声明"没有需求说明就先建议走 fe-req-analysis"，但在**真正空**的工作区里，模型调用了 `AskUserQuestion`（`-p` 模式下返回占位 `"Answer questions?"`）之后**仍然自行编造需求、直接写出 `fe-dev-购物车.md`**——违反 skill 自己的边界条款。这正是"两臂都挂"四象限里的"skill 臂不达标"，是 skill 质量信号而非评测噪声。
- **oracle 门禁拦下的 3 个用例编写错误**（0 token）：两个用例漏声明 oracle 产物；一个用例的案例级 oracle 与第 1 轮 must_not 冲突——都是先被门禁拒绝、修正后才允许花 token。
- **教训**：① 重跑必须先删目标目录（`cpSync` 是覆盖不是镜像）；② 产物断言默认要 `**/` 全深度；③ 跨轮断言要分"轮级"与"案例级"两层；④ 广度验证的价值恰恰在它暴露的是**评测器**的 bug，而不是 skill 的——三个"失败"里两个是 harness 问题、一个是夹具问题，只有最后一个是真发现。
- **影响文件**：`cc-eval/lib/assert.mjs`、`lib/glob.mjs`（新增）、`cc-eval.mjs`、`cases/*.json`×6、`fixtures/*`×6、`SPEC.md`。
- **回退**：删 6 个用例与夹具；harness 扩展保留（向后兼容，旧用例不受影响）。

---

## 文档（D1–D4 · 2026-09-12）

| 编号 | 文件 | 内容 |
|---|---|---|
| D1 | `skill-eval-research.md` | 调研总报告：§1 本机资产、§2–3 DSH 机制与实测、§5 评测设计、§9 网上最佳实践（附出处）、§10 多轮设计、§11 DSH 版实现、§12 同类工具对照、§13 建议 |
| D2 | `skill-eval/README.md`、`skill-eval/MANUAL.md` | DSH 版怎么跑 / 原理·结果·回归·移植 + 来源清单 |
| D3 | `cc-eval/SPEC.md`、`cc-eval/README.md`、`cc-eval/CHANGELOG.md` | Claude Code 版的能力说明书 / 快速上手 / 实现级改动记录 |
| D4 | `CHANGELOG.md`（本文件） | 总账 + 索引 + 口径约定 |

---


### CC18 · 2026-09-13 · 整理为可发布仓库（`agent-skill-eval`）

- **改了什么**：
  1. 新建仓库目录，收入 `cc-eval`（Claude Code 引擎）、`skill-eval`（DSH 引擎）、`shared`（Anthropic 兼容产物生成器）、`docs/research.md`（调研报告）、根 `CHANGELOG.md`（总账）；**排除** `out/` 运行产物、`node_modules`、临时探测脚本与下载的第三方文档；
  2. **可移植化**：两个引擎的 case `workspace` 全部改为相对路径（`fixtures/...`，相对各自项目根解析——`cc-eval.mjs` 与 `run.mjs` 各加一行 `resolve(HERE, ...)`）；`skill-eval` 新增 `SETUP.md` 说明两处机器相关配置（`overlay.yml` 的 file URL、插件对 DSH 安装的 junction）；
  3. **许可合规**：为 anthropics 的 `frontend-design`、`web-artifacts-builder` 夹具补齐原仓 `LICENSE.txt`（10KB/11KB）；根 `LICENSE` 采用 MIT，并在其中标注夹具来源与"fe-* 内部样本公开前需确认"的提醒；
  4. 新增根 `README.md`（能力一览 / 快速开始 / 实测基线 / 目录结构 / 许可）与 `.gitignore`；
  5. `git init -b main` + 首次提交（66 个文件）。
- **为什么**：准备上传 GitHub；源目录混有运行产物、机器绝对路径与第三方下载内容，不可直接发布。
- **证据**（在仓库目录内验证，非源目录）：
  ```
  node --check cc-eval.mjs   → 0
  cc-eval oracle             → 9/9 gate OK
  cc-eval run ping-skill --arms with_skill → PASS（5.4s，$0.115，退出码 0）
  git: 66 files, commit bbb6465 (main)
  ```
- **踩坑记录**：① PowerShell `Set-Content -Encoding utf8` 写出的 JSON 带 BOM，Node `JSON.parse` 直接挂——批量改 JSON 一律用 Node 读写；② PS 正则 `.*\\(a|b)\\` 转义出错会把字段写成空串（本次事故被原件备份救回）——改字段值不要用正则替换，用解析-修改-序列化。
- **影响文件**：整个仓库目录（新增）。
- **回退**：删除仓库目录；源目录（含运行产物）保持未动，仍是工作副本。

---


### CC19 · 2026-09-13 · 推送公开分支（`agent-skill-eval` → hophol/test-skill）

- **改了什么**：无代码改动；把净化后的公开版推上 GitHub 分支 `agent-skill-eval`（提交 `72fe4d2`，229 文件）。
- **净化范围**（公开版不含内部样本）：删除 4 个用例（`fe-req-analysis` / `fe-dev-design` / `fe-dev-chain` / `fe-test-design`）及 4 个夹具；README/SPEC/CHANGELOG 中内部样本细节已泛化并注明"仅私有版本包含"；净化后 `cc-eval oracle` 5/5 通过。
- **网络结论（这台机器）**：`github.com:443` HTTPS 间歇性阻断（换 4 个入口 IP、钉 hosts 均无效：TCP/TLS 时通时断）；**`ssh.github.com:443`（SSH over 443）稳定可用** → 远端改为 `ssh://git@ssh.github.com:443/hophol/test-skill.git`，新增 ed25519 密钥完成认证。
- **证据**：`ssh -T` 返回 "Hi hophol!"；`git push -u origin agent-skill-eval` → `4975459..72fe4d2`；`git ls-remote` 远端 sha === 本地 HEAD（`72fe4d2feb2b…`）——sha 一致即内容一致，fe-* 未上公开仓。
- **影响文件**：无（本地 `D:\Games\robot\agent-skill-eval` 的完整版未动，待推私有仓库）。
- **回退**：`git push origin --delete agent-skill-eval`。

---

### R6 · 2026-09-16 · 三方评测工具实测（OpenAI evaluate-skill / agentut / skill-up）

- **改了什么**：无评测框架代码改动；新增实测报告 `docs/three-tools-report.md` 与三个 demo 目录（`agentut-demo/`、`skillup-demo/`，plugin-eval 为稀疏克隆 `openai-plugins/`）。
- **做了什么**：
  1. **定位 OpenAI evaluate-skill 本体**：`openai/plugins`（skills 仓已弃用）的 `plugins/plugin-eval`——Node CLI + Codex 插件，不在 npm（private），本地 checkout 运行；官方博客 403，方法论（四段流水线 + Outcome/Process/Style/Efficiency 四分类）经第三方实测博客还原。
  2. **三工具全部真跑**：plugin-eval analyze（ping-check=100/A/96 tokens；frontend-design=**67/D/2131 tokens 超预算**）；agentut+opencode+DeepSeek（2 场景 2 passed，7.2s）；skill-up+claude_code（1 case PASS，13s，产物含 Anthropic 兼容 grading.json 与三态 result.json）。
  3. **环境打通**：git 走 SSH over 443；Go 从阿里云镜像 + goproxy.cn；opencode 配 DeepSeek provider（复用 DSH 凭证 key）。
- **结论（研究方向的输入）**：预算三段拆解（trigger/invoke/deferred）并入 L0；提示集四分类（显式/隐式/上下文/负向）；双 grader；agentut 式用例蒸馏；skill-up 可当第二意见 runner。详见报告 §5。
- **影响文件**：`docs/three-tools-report.md`（新增）、demo 目录（工作区，不入库）。
- **回退**：删除报告与 demo 目录。

---

### R7 · 2026-09-16 · 深度报告 v2：14 skill 语料批量 + 三工具源码级解析

- **改了什么**：新增 `docs/three-tools-report-v2.md`（取代 v1 为正式版，v1 保留为简版）。
- **做了什么**：
  1. **语料扩到 14 个真实 skill**（anthropics×7 / 内部样本×3（名称与产物在私有版本） / DSH×2 / ours×2），plugin-eval 批量体检：分数从 100/A 拉到 54/F，anthropics 富文档 skill 因预算超标集体 C-F（**基线带 Codex 立场**的重要洞察）；
  2. **plugin-eval 底层全解并数值验证**：token=ceil(len/4)；trigger=name+desc（policy 感知）、invoke=SKILL.md 全文、deferred=其余文本；基线=常量或本机 p50/75/90；**score=100−Σ(严重度权重×状态系数)**，三例实测回验全部吻合（67/54/58）；
  3. **agentut 底层**：一切落在 matchValue() 五档 Matcher（equals>contains>containsOneOf>regex>oneOf，无效正则→false）；断言分=round(通过/总数×100)；runs/min_pass 三级覆盖；distiller 按 user 消息切 step；
  4. **skill-up 底层**：Judge(Input)→Result 统一接口；expect 7 规则**短路省 token**；rule_based **failure 优先**；agent_judge 严格 JSON+重试一次+pass_threshold 0.7；多轮 SessionResumer；统一信号量并发池；
  5. **三角对照实验**：frontend-design 同一 skill 三工具（plugin-eval 67/D 静态 / skill-up PASS 但 240s 超时需 600s / cc-eval PASS 107s lift=1）——单一视角都会误判；
  6. **skill-up 评真实 skill 首次超时**（240s context deadline）→ 复跑 600s 通过，与 cc-eval webart 超时互相印证"执行型/富文档 skill 需要分级超时"。
- **方向修订**：P0=静态预算审计进 L0（自建分位数基线、中文用真 tokenizer）+ 断言 DSL 升级（五档 Matcher + 加权）；P1=Judge 接口抽取、LLM 裁判、分级超时。详见报告 §6/§7。
- **影响文件**：`docs/three-tools-report-v2.md`（新增）；demo 与语料目录为工作区产物不入库。
- **回退**：删除该文件。

---

### R8 · 2026-09-16 · 结构篇调研报告（每个能力的结构全量铺开）

- **改了什么**：新增 `docs/capability-structures-report.md`（v3 结构篇，与 v2 逻辑篇配套）。
- **内容**：plugin-eval（27 文件模块树 + EvaluationResult/Check/Metric/Artifact 四构造器源码原文 + 扩展点）；agentut（模块树 + YAML 三层结构 + 45 类型中的 8 组关键类型 + MockRule）；skill-up（19 个 internal 包树 + config/schema.go 全部 35 类型逐字段含 yaml 标签 + Judge.Input/Result + EvalResult + 产物目录树）；速览 skillgrade/comet/skill-eval-harness/官方 evals.json；cc-eval 对照。
- **三个结构级洞察**：判分输入字段集是表达力分水岭（轮级断言靠 Input 带 Transcript/Turns）；官方 evals.json 是交换格式而非表达格式；扩展点三哲学（加文件/加 union/加接口）。
- **行动项**：Check/Metric/Artifact 三构造器进断言层；judge(Input) 接口化；Matcher 五档；用例 schema 补 capture 与 git context；components 级可追溯。
- **影响文件**：`docs/capability-structures-report.md`（新增）。

---

## 下一批计划（执行后逐条补记录）

| 计划 | 触发条件 | 预期证据 | 预估成本 |
|---|---|---|---|
| ~~`cc-eval run --repeats 3` 出真统计~~ **已完成（CC14）** | — | 每臂 3/3 vs 0/3、macro lift=1、canary ok | 实际 $1.45 / 8 分钟 |
| ~~产物同时输出 Anthropic 兼容格式（统一两引擎）~~ **已完成（CC15）** | — | 两引擎 `run_summary` 形状一致、canary 已剔除 | 低 |
| judge 层（确定性优先，LLM 兜底） | 出现主观维度用例 | 报告新增 judge 分区且**不参与**退出码 | 中 |
| ~~并发 + 每 case 独立工作区~~ **已完成（CC16）** | — | 15 任务 166s vs 串行约 8 分钟（≈2.9×），成本持平 | 实际 $1.42 |
| 失败模式切片 | 用例数上来 | 报告按 failure mode 分组 | 中 |
| CI 接入 | flakiness 基线摸清 | 形态校验硬门先行，通过率门后置 | 中 |
| （R5 产出）回归判定：指名断言翻转 + ≥6 对 paired sign-flip | 需要版本对比时 | 报告输出 `regressions[]` 与 INDETERMINATE | 低 |
| （R5 产出）消融臂 / old_skill 快照臂 | 回归判定落地后 | `--variant ablation:xxx` | 中 |
| （R5 产出）judge 三段校准 | 引入 judge 层时 | robustness/alignment/compare 三份报告 | 中 |
| （R5 产出）核对官方 `claude plugin eval`（升级 CLI 后） | CLI ≥2.1.233 | 与 cc-eval 的能力对照表，决定分工 | 低 |

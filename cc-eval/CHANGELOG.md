# CHANGELOG — cc-eval（分账）

> 总账在 **`../CHANGELOG.md`**：所有项目的每一步改动都记在那里；本文件保存 cc-eval 的**实现级细节**（方案 B）。

> **约定：每一步改动都必须在这里留一条记录**（代码、用例、夹具、判据、文档、参数默认值都算）。
> 每条记录必须包含五样东西：**改了什么 / 为什么改 / 证据（命令 + 观测到的数字或输出）/ 影响文件 / 怎么回退**。
> 只跑评测不改代码时，也算一条（记运行结果与花费）。
> 记录**只追加、不修改**；写错了就再追加一条更正。

---

## v0.1.0 — 2026-09-12

### 背景（同日早些时候，两个前置阶段）

| 阶段 | 产出 | 记录位置 |
|---|---|---|
| 调研 | 最佳实践（Anthropic skill-creator / skilljack / SkillsBench / crashcart / addyosmani / groundwork / rsc 等 38 份原文）+ 同类工具对照（alibaba/skill-up、agentut） | `../skill-eval-research.md`（§9 最佳实践、§12 工具对照、§12.4 默认值、§12.5 战略建议） |
| DSH 引擎版 | 多轮 runner 插件 + 两臂 A/B + oracle/canary + 3 次重复统计 | `../skill-eval/`（`MANUAL.md`、`README.md`） |

目标定位调整：**先把评测能力对准 Claude Code**（本文件的 `cc-eval`），DSH 版保留为同源的另一引擎适配器。

---

### C1. 可行性验证：Claude Code 能否无人值守跑

- **改了什么**：无代码改动，仅探测。
- **为什么**：评测器的前提是能非交互驱动 Claude Code 并拿到结构化事件。
- **证据**：
  - `claude -p "reply with exactly OK" --output-format json` → `exit 0`，返回 `result:"OK"`、`session_id`、`total_cost_usd:0.0988`、`num_turns:1`、`modelUsage` 键为 `glm-5.3`（说明本机走自定义路由）。
  - `claude --help` 确认存在 `-p/--print`、`--output-format stream-json`、`--resume`、`--permission-mode`、`--allowedTools`、`--dangerously-skip-permissions`。
- **影响文件**：无（探测目录 `../cc-probe/`）。
- **回退**：删除 `../cc-probe/`。

### C2. 可行性验证：skill 触发可被确定性观测

- **改了什么**：在探测工作区放入 `.claude/skills/ping-check/SKILL.md`，跑 `claude -p "帮我做一次 ping 检查" --output-format stream-json --verbose`。
- **为什么**：需要确定"skill 是否生效"的判据长什么样。
- **证据**（解析 130 条事件）：
  - `system/init` 的 `tools` 列表含 `Skill`、`AskUserQuestion`；
  - 工具序列：`Skill {\"skill\":\"ping-check\"}` → `tool_result: "Launching skill: ping-check"`；
  - 最终文本 `PING-SKILL-OK`；`result` 事件 `num_turns:3`、`duration_ms:4402`、`total_cost_usd:0.0315`、`usage{input:1276,output:143,cache_read:41536}`。
- **影响文件**：无（后续转化为 `fixtures/ping/`）。
- **回退**：同上。

### C3. 建立 cc-eval 骨架

- **改了什么**：新增 `cc-eval.mjs`（`oracle`/`run`/`report` 三个子命令）、`lib/assert.mjs`（断言库，runner 与 oracle 共用）、`lib/stats.mjs`（统计 + Anthropic 兼容产物）、`package.json`。
- **为什么**：把"两臂 + 按轮断言 + 防自欺 + 统计"落成一个可直接跑的 CLI。
- **关键实现**：每轮一个 `claude -p` 进程、全程 `--resume` 同一 `session_id`；**stdout 用文件 fd 而非管道**（`stdio:['ignore',fd,fd]`），避免大流截断与沙箱管道限制。
- **证据**：`node cc-eval.mjs oracle` 后续通过（见 C5）。
- **影响文件**：`cc-eval.mjs`、`lib/assert.mjs`、`lib/stats.mjs`、`package.json`。
- **回退**：删除该目录。

### C4. 用例与夹具

- **改了什么**：新增三个用例 `cases/{ping-skill,clarify-multiturn,canary-never}.json` + `cases/INDEX.txt`，以及夹具 `fixtures/{ping,clarify,empty}/workspace`（`.claude/skills/<skill>/SKILL.md`）。
- **为什么**：`ping-skill` 验证"skill 是否被加载"的最短路径；`clarify-multiturn` 验证"提问型 skill + 多轮"；`canary-never` 做判分器负向控制。
- **证据**：`oracle` 三条全 OK（C5）。
- **回退**：删除对应文件。

### C5. oracle gate 通过

- **改了什么**：无（跑自检）。
- **证据**：`node cc-eval.mjs oracle` →
  `ping-skill gate: OK` / `clarify-multiturn gate: OK` / `canary-never gate: OK` → `oracle gate: all cases solvable by construction`。
- **意义**：判据可达（正向控制）+ 判据会失败（负向控制）都被证明，0 token。

### C6. 首次真跑 `ping-skill`（两臂）

- **证据**：
  ```
  ping-skill/with_skill#1    turn 1 tools=[Skill]        assert=PASS
  ping-skill/without_skill#1 turn 1 tools=[Glob,Bash,Bash] assert=FAIL(must_call_skill, must_contain)
  ```
  耗时 7.7s vs 38.1s；成本 $0.0363 vs $0.1834。
- **观测**：退出码当时为 1——**因为无 skill 臂失败**。这暴露了退出码语义问题（见 C10）。

### C7. 首次真跑 `clarify-multiturn`，暴露判据过宽

- **证据**：`with_skill` 第 2 轮 `tools=[Write,Glob]` → `FAIL(must_not_ask)`；但同轮 `must_write_file` 已通过。
- **根因**：`must_not_ask` 与 `must_ask_user` 共用同一个宽松判据（"回复里有问号"）。模型写完 `plan.md` 后礼貌地问了句"需要我继续吗？"就被判失败——**假失败**。
- **改了什么**：`askedUser(turn, mode)` 拆成两种严格度：
  - `must_ask_user` → `text_or_tool`（宽松：工具调用**或**问号）；
  - `must_not_ask` → `tool`（严格：只认 `AskUserQuestion` 工具调用）；
  - 新增子句级 `must_not_reask: [关键词]`，只有**带问号的子句**里出现关键词才算重复追问。
- **影响文件**：`lib/assert.mjs`、`cases/clarify-multiturn.json`。
- **回退**：恢复 `askedUser(turn)` 单判据并去掉 `must_not_reask`。

### C8. 第二次跑仍失败，暴露正则恒真 bug

- **证据**：`turn 2 tools=[Write,Read] assert=FAIL(must_not_reask)`；而同轮模型文本实际是"已确认:平台为阿里云 ECS,截止下周五(2026-09-18)前上线…"——**并没有提问**。
- **根因**：实现写成 `if (!/[?？]/.test(s + '?')) continue`——给每个子句补了个问号，条件**恒真**，于是任何提到关键词的句子都被当成"追问"。
- **改了什么**：改为 `text.match(/[^。！!？?\n]*[？?]/g)`，直接取出带问号的子句，不再人工补问号。
- **影响文件**：`lib/assert.mjs`。
- **回退**：恢复上一版实现（但不要回退到"补问号"的写法）。

### C9. 第三次跑 `clarify-multiturn`（skill 臂）通过

- **证据**：`turn 1 tools=[Skill,AskUserQuestion] PASS` → `turn 2 tools=[Write,Read] PASS`；`turns=2 wall=27.5s cost=$0.1132 EXIT=0`。
- **附带观测**：headless 下 `AskUserQuestion` 的 `tool_result` 是占位文本 **"Answer questions?"**（拿不到真实答案）→ 提问型 skill 只能靠下一轮用户消息给答案。已写入 SPEC §2/§4。

### C10. 退出码语义修正

- **改了什么**：`run` 的退出码改为只对 **skill 臂是否全部达标** 负责（外加：canary 通过 = 判分器损坏、`aborted` = 运行被中止，都判失败）。基线臂失败**不再**影响退出码。
- **为什么**：基线失败是 lift 的来源、是**预期结果**；把它当失败会让 CI 永远红。
- **证据**：全量跑（C12）`EXIT=0`，其中两个基线臂均为 FAIL。
- **影响文件**：`cc-eval.mjs`。
- **回退**：恢复"任一 run 失败即非 0"。

### C11. 统计字段修正

- **改了什么**：`armStats` 读 `r.numTurns` 改为 `r.turnsUsed`。
- **为什么**：报告里 `turns` 恒为 0（run 报告里字段名是 `turnsUsed`）。
- **证据**：修正后 `report` 输出 `turns=1` / `turns=2`（修正前是 `turns=0`）。
- **影响文件**：`lib/stats.mjs`。
- **回退**：无必要。

### C12. 全量跑（3 用例 × 2 臂，各 1 次）并出报告

- **证据**：
  ```
  ping-skill        with_skill 1/1 PASS turns=1  6.8s  $0.1229  tools=[Skill]
                    without    0/1 FAIL turns=1 35.3s  $0.0935  tools=[Bash×4]
  clarify-multiturn with_skill 1/1 PASS turns=2 27.3s  $0.1160  [Skill,AskUserQuestion]→[Write,Read]
                    without    0/1 FAIL turns=2 67.3s  $0.1654  [Bash,Glob,AskUserQuestion]→[Bash]
  canary-never      with_skill 0/1 FAIL（应当失败） 4.0s $0.0217
  macro lift = 1 | canary = ok | 合计 $0.5193 | EXIT=0
  ```
- **产物**：`out/runs/<case>.<arm>.run<k>/{report.json, grading.json, turn-*.jsonl}`、`out/summary.json`、`out/benchmark.json`。
- **花费**：约 0.52 美元、约 2.5 分钟（串行）。

### C13. 文档

- **改了什么**：新增 `SPEC.md`（能力说明书：定义/约束/架构/驱动细节/用例/断言目录/防自欺/结果口径/基线与坑/路线图）、`README.md`（快速上手 + 实测 + Claude Code 硬事实 + 两条判据教训）、本 `CHANGELOG.md`。
- **为什么**：能力要能被别人接手；改动要可追溯。
- **证据**：文件即产物。
- **回退**：删除对应文档（不建议）。

### CC14. 3 次重复跑出真统计（P0，2026-09-12）

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

## 下一批计划（尚未执行，执行后逐条补记录）

| 计划 | 触发条件 | 预期证据 |
|---|---|---|
| P0 用 `--repeats 3` 跑全量，出 Wilson 区间与 lift 稳定性 | 用户确认后 | `out/summary.json` 中每臂 `runs=3`、`ci95Wilson` 与 `lift` |
| P1 增加 judge 层（确定性优先，LLM 只兜底质量类） | 有主观维度用例时 | 报告新增 judge 分区，且**不参与**退出码 |
| P1 并发 + 每 case 独立工作区 | 基线臂耗时成为瓶颈时 | 全量墙钟对比 |
| P2 失败模式切片 | 用例数上来后 | 报告按 failure mode 分组 |
| P2 CI 接入 | flakiness 基线摸清后 | 形态校验硬门先行 |

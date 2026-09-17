# 三方 skill 评测能力深度报告 v2：plugin-eval · agentut · skill-up

> 日期：2026-09-16 · v2 取代 v1（three-tools-report.md 保留为简版）
> 方法：**14 个真实 skill 语料批量实测 + 三工具源码逐行解析**（plugin-eval 的 src/、skill-up 的 internal/、agentut 的 src/，均在本地克隆/安装后直读）
> 本报告回答：每个能力**是怎么做到的（到最底层逻辑）**、实测结果如何、我们该往哪研究。

---

## 0. 一页结论

| | plugin-eval（OpenAI） | agentut | skill-up（alibaba） |
|---|---|---|---|
| 本质 | **纯静态分析器 + token 预算审计**（不跑模型） | **单测式回放器**（opencode 引擎 + 断言） | **声明式评测框架**（多引擎 + 三层 judge） |
| 最底层的一句 | 一切都从 'ceil(字符数/4)' 这个token估算出发 | 一切都落在 'matchValue()' 这个 50 行的匹配函数上 | 一切都过 'Judge.Evaluate(Input)→Result' 这一个接口 |
| 实测规模 | 14 skill 批量（0 成本） | 2 场景（7.2s） | 2 skill × 2 次运行（13s / 195s+1 次超时） |
| 最深印象 | frontend-design 2131 tokens → D 级；打分公式数值验证 3 例全吻合 | 断言全是工具级硬信号；7 秒出结果 | expect 短路省 token；真实 skill 240s 会超时 |

---

## 1. 语料与批量实测（plugin-eval，14 个 skill，零模型成本）

| skill | 来源 | score | grade | fail/warn | trigger | invoke | deferred |
|---|---|---|---|---|---|---|---|
| ping-check | ours | 100 | A | 0/0 | 8 | 88 | 0 |
| scope-check | ours | 100 | A | 0/0 | ~30 | ~300 | 0 |
| 文档型 skill ×3 | 内部样本（私有版本） | 95 | A | 0/1 | 小 | 中 | 0 |
| doc-coauthoring | anthropics | 77 | C | 1/2 | — | — | — |
| brand-guidelines | anthropics | 77 | C | 1/2 | — | — | — |
| web-artifacts-builder | anthropics | 77 | C | 1/2 | — | — | — |
| dsh-code-review | DSH 仓 | 72 | C | 2/0 | — | — | — |
| frontend-design | anthropics | 67 | D | 2/1 | **55** | **2359** | **2588** |
| canvas-design | anthropics | 67 | D | 2/1 | — | — | — |
| mcp-builder | anthropics | 58 | D | 2/3 | — | — | — |
| dsh-prose-standard | DSH 仓 | 58 | D | 3/0 | — | — | — |
| webapp-testing | anthropics | **54** | **F** | 2/4 | — | — | — |

（完整逐项 budgets/checks 在 _pe_results.json；上表 trigger/invoke/deferred 为 tokens 估算值，"—"表示未逐项摘录，见附录复现命令。）

**一眼结论**：我们/内部的精简文档型 skill 全 A；**anthropics 官方 skill 因"正文+引用太大"集体 C-F**——因为它们的阈值基线是 **Codex 的轻目录习惯**，不是为"人读的富文档"设计的。这本身就是重要洞察：**静态预算分是有立场 的，跨引擎解读要小心**。

---

## 2. plugin-eval：底层逻辑全解

### 2.1 架构与数据流

~~~
evaluators/{skill,python,typescript,coverage,plugin}.js   ← 产出 checks[]
        ↓
core/scoring.js        penalty=权重×状态 → score=100−Σ → grade
core/budget.js         trigger/invoke/deferred 三段估算
core/baseline.js       阈值来源（常量 or 本机分位数）
renderers/{markdown,json,html}.js
~~~

### 2.2 token 估算（最底层）

src/lib/tokens.js 全文即：

~~~
export function estimateTokenCount(text) {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}
~~~

**字符数除以 4**——没有 tokenizer、不分语言（中文按此估算会显著偏低）。所有"预算"结论都建立在这个一行的估算器上。

### 2.3 预算三段的精确定义（core/budget.js）

对每个 skill 目录：

- **trigger_cost_tokens** = name 的 tokens + description 的 tokens（各 ceil(len/4)）。**前提**是 'agents/openai.yaml' 里 'policy.allow_implicit_invocation !== false'——如果 skill 声明"只许显式调用"，trigger 记 0（方法名变为 estimated-static-policy-aware）。frontend-design 实测：name=4 + description=51 = 55。
- **invoke_cost_tokens** = **SKILL.md 整个文件**（含 frontmatter）的 tokens。frontend-design = 2359。
- **deferred_cost_tokens** = 目录里**其余所有"疑似文本文件"**逐个估算求和（references/、脚本、LICENSE 等）。frontend-design = 2588。

每段都保留 components[{label, path, tokens, note}]，所以报告能指到具体文件。

### 2.4 阈值基线（core/baseline.js）

- **常量默认**（skill）：trigger [48,92,150]、invoke [220,480,900]、deferred [180,520,1200]；plugin 与 directory 另有矩阵。
- **动态基线**：若本机 '~/.codex/skills' 与 curated 插件缓存里能采到 ≥4 个样本，则用它们的三段值取 **p50/p75/p90** 作为 [goodMax, moderateMax, heavyMax]——即"和 你机器上装的一比"。
- **band 判定**：value≤goodMax→good；≤moderateMax→moderate；≤heavyMax→heavy；否则 excessive。

### 2.5 打分公式（core/scoring.js）——已数值验证

~~~
SEVERITY_WEIGHT = { error: 14, warning: 6, info: 1 }
STATUS_MULTIPLIER = { fail: 1, warn: 0.75, info: 0.25, pass: 0 }
penalty(check) = WEIGHT[severity] × MULTIPLIER[status]
score = 100 − Σ penalty          （startingScore 100）
GRADE = A≥93 | B≥85 | C≥70 | D≥55 | else F
~~~

用本批实测回验：
- frontend-design：2×(error×fail=14) + 1×(warning×warn=4.5) = 32.5 → **67.5 → 显示 67/D** ✓
- webapp-testing：28 + 4×4.5=18 → 46 → **54/F** ✓
- mcp-builder：28 + 3×4.5=13.5 → 41.5 → **58/D** ✓

排序（Fix First）按 penalty 降序，同分按 status/category 优先级；每类 check 有内置"why"文案（budget 类："always-loaded text can make the workflow feel expensive fast"）。

### 2.6 checks 家族（evaluators/）

- skill.js：frontmatter 合法性、description 是否含明确触发语（description-trigger-weak）等；
- python.js / typescript.js：**对 skill 里的脚本做代码质量检查**（圈复杂度 py-complexity-high、超长行、缺配套测试 py-tests-missing）；
- coverage.js：找 lcov.info / coverage.xml / Istanbul JSON，有则计覆盖率（没有则 info 级扣 0.25）；
- plugin.js：.codex-plugin/plugin.json 清单校验。

### 2.7 评价

- **强**：零成本、可批量、公式完全可解释（我们能手工复算每个分数）；预算三段是独家维度；policy 感应很细。
- **弱**：不跑模型（"估算 ≠ 实测"，它自己也强调 observed usage 才是真相）；len/4 对中文失真；基线带 Codex 立场；无对照组概念。

---

## 3. agentut：底层逻辑全解

### 3.1 数据流

~~~
YAML(environments/scenarios/steps) 
  → 复制 fixture 到 $WORKDIR（.agentut/temp/…）+ setup.copy 挂 skill 到 .opencode/skills/
  → 逐 step 起 'opencode run "<input>" --format json'（同场景共享会话）
  → 收集 OpenCodeRunOutput[]（JSONL 事件）
  → verifier：outputs + workDir 双向验断言
  → 计分（断言分 or judge 分）→ runs/min_pass 聚合
~~~

### 3.2 断言引擎的核心：matchValue（src/executor/verifier.ts，逐行读过）

~~~
字符串 matcher = equals 精确匹配
Matcher 对象按**优先级**只认第一个存在的字段：
  equals        → actual === matcher.equals
  contains      → String(actual).includes(...)
  containsOneOf → 任一子串命中
  regex         → new RegExp(...).test(...)（无效正则 → false，不抛错）
  oneOf         → 候选值之一
~~~

7 种断言全部建立在这个函数上：
- should_call_tool / should_not_call_tool：匹配 {name, input:{k:matcher}, output, status}——**工具名简写大小写不敏感（转小写），Matcher 形式则大小写敏感**；status ∈ completed/error/pending；
- should_produce_file：递归收集 workDir 相对路径后匹配；
- file_content_contains / response_contains / exec_command（spawn shell 执行并匹配 stdout+stderr，超时走 treeKill 防孤儿进程）/ judged_by（AI 裁判，输出需过三层兜底解析：纯 JSON→严格正则→宽松正则，解析不到一律判 fail）。

### 3.3 计分模型

~~~
有 score.prompt → 裁判返回 {score, reason}，clamp(0..100)
没有 → 断言分 = round(通过断言数 / 总断言数 × 100)，reason 固定 "judge score by assertion"
场景总分 = Σ(场景分×priority)/Σ(priority)   （priority 默认 10）
多次运行：每 run 独立评分取平均；min_score 施加在平均分上
~~~

概率判定：config.runs（默认 5）/ min_pass（默认 4，即 80%）三级覆盖（CLI > scenario > global）；通过需"场景 passed_runs≥min_pass **且每条断言自身** passed_runs≥min_pass"。

### 3.4 distiller（从真实会话长用例）

按 **user 消息切 step**；assistant 消息抽四类信号：reasoning（截断 200 字符）、tool 调用（名/状态/入参/输出/错误）、最终文本、文件变更（message.info.summary.diffs，去重）。给裁判的 formatForJudge() 明确"只输出事实描述，不含任何指令"（抗注入）。

### 3.5 实测与评价

- 实测：2 场景（正例 should_call_tool{Skill, name:ping-check, status:completed} + response_contains PONG-SKILL-OK；负例 should_not_call_tool）→ **2 passed，7.2s**，模型 deepseek-official/deepseek-chat（opencode 1.18.31）。
- **强**：断言是工具级硬信号；安装即用；双场景 7 秒。
- **弱**：仅 opencode 引擎；无对照组（测不出增量）；'-o' 落盘在 Windows 上没写出文件（stdout 正常）；无 token 成本视角。

---

## 4. skill-up：底层逻辑全解

### 4.1 分层架构（internal/）

~~~
cli → runner（端到端编排）→ evaluator（case×configuration 统一信号量并发池）
                                   ↓
                        agent（claude_code/codex/qoder 适配器）+ runtime（none/opensandbox）
                                   ↓
                        judge：expect(短路闸) → rule_based | script | agent_judge
                                   ↓
                        report（JSON/JUnit/HTML + Anthropic grading.json）
~~~

### 4.2 Judge 统一接口（internal/judge/judge.go）

Input = {CaseID, Transcript, FinalMessage, ExitCode, WorkspacePath, WorkspaceDiff, GeneratedFiles, TurnsExecuted, TurnsTotal, SessionResult…}；Result = {Status, AssertionResults[{Text,Passed,Evidence}], Summary}。**所有判分实现吃同一个 Input**——这就是"判分与引擎解耦"的落点。

### 4.3 Expect 短路闸（expect.go）

7 条零成本检查（must_contain/must_not_contain/exit_code/files_exist/files_not_exist/golden_file/file_contains）；**任一失败直接出 FAIL，不再调 Judge——省 token 是设计目标而非优化**。

### 4.4 三种 Judge

- **rule_based**（19KB）：声明式规则；**failure 规则先评（任一命中→FAIL），success 后评（全中才 PASS）**；规则含 output_contains{all/any/not}、output_matches（Go 正则）、tool_called（含参数部分匹配）、files_exist 等。
- **script**：外部脚本，cwd=case workspace，注入 EVAL_TRANSCRIPT_PATH / EVAL_FINAL_MESSAGE / EVAL_EXIT_CODE；**退出码 0=PASS**；默认 30s 超时。
- **agent_judge**（32KB）：LLM 裁判。关键契约：criteria 逐一编号，输出必须是**单个严格 JSON**（可包一层代码围栏，多余字段/尾随内容拒绝）；每条需 criterion_id/passed/非空 evidence/显式 failures；**解析失败精确重试一次**（共享原超时预算，只要求修正输出契约）；**pass_rate ≥ pass_threshold（默认 0.7）才 PASS**。

### 4.5 evaluator 与多轮

- 并发：cases × (with_skill + without_skill) 全部进**一个信号量工作池**（无按臂独立池）；
- EvalResult 携带 usage（input/output tokens）、turns、judge session、expect 结果；
- 多轮（multiturn.go + SUP-0001 设计）：turn1 'Agent.Run' 建会话回填 SessionID，turn2..N 'SessionResumer.RunTurn(sessionID)'；引擎侧分别是 claude '--resume' / codex 'codex resume' / qoder '-r'；**不支持 resume 的引擎只有在无 post_condition/capture/轮级规则时才允许拼接回退，否则判 ERROR**。

### 4.6 实测与评价

- ping-check：validate → run → **PASS 100%（13s）**；产物含 Anthropic 兼容 grading.json（expectations[{text,passed,evidence}]）与三态 result.json（requested/applied/**observed=claude 2.1.170**）+ 原始 claude 轨迹 jsonl。
- frontend-design（真实 skill）：**240s 超时判 ERROR**（context deadline exceeded）；放宽到 600s 后 **PASS（195s）**——真实 skill 的执行时长是硬约束。
- **强**：声明式+全量 validate；判分分层彻底；产物生态位（Anthropic 形状）。
- **弱**：without_skill 默认不跑；统计只有 mean/delta；agent_judge 阈值硬编码 0.7；超时语义是"整 case deadline"而非轮级。

---

## 5. 三角对照：同一个 frontend-design，三种视角

| 工具 | 视角 | 结果 | 耗时/成本 |
|---|---|---|---|
| plugin-eval | 静态：结构+预算 | **67/D**（invoke 2359 + deferred 2588 超基线；description 缺"Use when"） | 0 token，秒级 |
| skill-up | 行为：单臂断言 | **PASS**（回复含配色/字体）；**240s 超时一次**，600s 档通过 | 195s，约 2 万+ token |
| cc-eval（我们） | 行为：两臂 lift | with_skill **1/1 PASS**、without **0/1**，**lift=1**（基线连 Skill 都不调） | 107.5s/$0.20 |

**读法**：三者回答的是三个不同的问题——"写得贵不贵/规范吗"（67/D）、"触发后能不能干活"（PASS）、"相对没有它有没有增量"（lift=1）。**任何一个单独看都会误判**：静态 D 级的 skill 行为完全正常且增量明确。

---

## 6. 与 cc-eval 的能力映射（哪一层抄谁）

| 能力层 | 现状 | 抄谁 | 怎么抄 |
|---|---|---|---|
| token 预算三段 | 无（只有事后 usage） | plugin-eval | L0 加静态估算：trigger=name+desc、invoke=SKILL.md、deferred=其余文本；band 用自己语料的 p50/75/90（**别用 Codex 常量**，中文语料失真） |
| 打分可解释性 | 布尔断言 | plugin-eval | penalty 矩阵（严重度×状态）可借给"断言加权"：must_call_skill 设为 error 级、must_contain 设 info 级 |
| 断言匹配 DSL | 精确/glob 两极 | agentut | matchValue 的五档 Matcher（equals/contains/containsOneOf/regex/oneOf）直接并入 assert.mjs，~50 行 |
| 判分/引擎解耦 | 耦合在 executeRun | skill-up | 抽 Judge(Input)→Result 接口；Input 已齐（turns/workspace/transcript） |
| expect 短路 | 无 | skill-up | 断言分两档：零成本档（文件/文本）先跑，失败即跳过昂贵档 |
| LLM 裁判 | 无 | skill-up agent_judge | 严格 JSON + criterion_id/passed/evidence + 失败重试一次 + pass_threshold（0.7 起步，但要可配） |
| 轮级超时 | 有（每轮） | skill-up 的教训 | 保留轮级 + 加整 case deadline 双保险（真实 skill 会超整 case） |
| 会话蒸馏生成用例 | 无 | agentut distiller | 从 ~/.claude/projects 的 jsonl 切 step 抽工具调用/文件变更（DSH 版已有转录解析零件） |

---

## 7. 研究方向（v2 修订，按优先级）

1. **静态预算审计进 L0**（P0）：三段估算 + 自建语料分位数基线 + band。零成本、立刻可做，且是唯一覆盖"贵不贵"的维度。注意中文 token 估算要用 tokenizer 而非 len/4（plugin-eval 的失真点，正好是我们的改进点）。
2. **断言 DSL 升级**（P0）：并入五档 Matcher + 断言加权（severity×status）——两个都是小改动，表达力和可解释性立刻上台阶。
3. **Judge 接口抽取**（P1）：判分从 runner 里解耦，为 expect 短路、script judge、LLM 裁判铺路。
4. **LLM 裁判层**（P1）：按 skill-up 契约实现（严格 JSON/重试一次/threshold），配 R5 的三段校准（负控/kappa/compare），不参与退出码。
5. **真实 skill 时长治理**（P1）：本轮两个实测（skill-up 240s 超时、cc-eval webart 600s 超时）都指向同一件事——执行型/富文档 skill 需要分级超时与"部分完成也可判分"的断言布局。
6. **用例蒸馏**（P2）：从真实 Claude Code 会话生成回归用例（agentut 思路 + 我们已有的转录解析）。
7. **不做**：静态检查器整造（plugin-eval 够用且可解释）、多引擎适配层（skill-up 覆盖）。

---

## 8. 附录

### 8.1 复现命令（本机路径）

~~~
# plugin-eval 批量（14 skill）
node D:/Games/robot/openai-plugins/plugins/plugin-eval/scripts/plugin-eval.js analyze <skill目录> --format json
# 批量脚本与结果：_pe_batch.mjs / _pe_results.json

# agentut（opencode + DeepSeek）
cd D:/Games/robot/agentut-demo && agentut run tests/ping-test.yaml

# skill-up
cd D:/Games/robot/skillup-demo/ping-check && D:/Games/robot/_gobin/skill-up.exe run
cd D:/Games/robot/skillup-demo/frontend-design && ... run   # timeout_seconds 需 600
~~~

### 8.2 语料清单

anthropics（frontend-design/canvas-design/mcp-builder/doc-coauthoring/brand-guidelines/web-artifacts-builder/webapp-testing）· 内部样本 ×3（私有版本） · DSH 仓 ×2（dsh-code-review/dsh-prose-standard）· ours ×2（ping-check/scope-check）

### 8.3 源码解析位置

plugin-eval：src/lib/tokens.js（全文 10 行）、src/core/{budget,baseline,scoring}.js、src/evaluators/*
skill-up：internal/judge/{README,judge,expect,rule_based,script,agent_judge}.go、internal/evaluator/{README,evaluator,multiturn}.go
agentut：src/executor/verifier.ts（matchValue）、src/distiller/opencode.ts、src/types/index.ts

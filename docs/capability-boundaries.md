# 评测工具的能力与能力边界——基于 5 个真实 Skill 的全流程实测

> 核心问题：这些评测工具能做什么、做不到什么、边界在哪里。
> 不关注分数高低，只关注能力的覆盖范围和盲区。
> 数据来源：5 个跑了完整行为评测的 skill，工具调用链和产物均从评测报告中直接提取。

---

## 一、被测 Skill：干了什么、产出了什么

### us-breakdown（US 拆解，含 2 个 CLI 脚本）

这个 skill 要求 agent 执行一个六步工作流：读 US 文件、运行解析脚本、按规则生成任务、写两个产物文件、运行校验脚本、回复总结。

**agent 实际执行的工具序列**（从评测报告提取）：

~~~
Skill → Read → Read → Read → Bash(us_parser.mjs) → Read → Write(breakdown.json) → Write(tasks.md) → Bash(validate_breakdown.mjs)
~~~

**产出的东西**：
- breakdown.json 文件，包含全部 3 条验收标准和对应的任务（每个任务有 id、关联的 AC、标题、估点天数、测试提示）
- tasks.md 文件，人类可读的任务清单表格
- 校验脚本返回 exit 0（通过）
- 第 2 轮追加 AC4 后，重新生成产物并重跑校验

**关键行为**：agent 真的用 Bash 执行了两个 Node.js 脚本——不是肉眼看了脚本源码后手工推演。

### product-manager（PM 全流程，多 agent 协作）

这个 skill 描述了一个五人 agent 团队的协作流程，但测试时只装了 SKILL.md（没有子 agent 定义文件）。

**agent 实际执行的工具序列**：

~~~
Skill → Read → Glob → Glob → TaskCreate ×3 → Write ×2 → TaskUpdate ×3 → Agent → Read → Read → Write → TaskUpdate ×2 → Agent → Read → Read → Read → Write → Read → Read → Read → Edit ×9 → TaskUpdate ×2
~~~

**产出的东西**：
- _workspace/03_user_stories.md 文件，标准格式的用户故事（As a / I want / 验收标准）
- 多个中间产物（通过 Write 和 Edit 逐步构建）

**关键行为**：agent 没有真正的子 agent 定义文件可用，于是**用内置的 Agent 工具即兴模拟了多个角色**——它读了 SKILL.md 里描述的工作流后，自己编排了类似的多 agent 协作。

### tdd-guide（TDD 测试编写指南）

一个 403 行的详细 TDD 工作流指南。

**agent 实际执行的工具序列**：

~~~
Skill → Read → Glob ×4 → Bash ×3 → AskUserQuestion → TaskCreate ×3 → Bash → TaskUpdate → Write ×3 → Bash → TaskUpdate ×2 → Write → Bash ×4 → Edit ×2 → Bash ×2 → TaskUpdate ×2
~~~

**产出的东西**：
- 测试文件（通过 Glob 找到源码，Write 生成测试代码，Bash 运行 npm test 验证通过）
- 覆盖 formatDate 的多种用例

**关键行为**：agent 用 AskUserQuestion 向用户确认了测试框架选择——这是 skill 里教的行为之一。

### root-cause-analysis（根因分析调试）

一个 174 行的结构化调试方法论。

**agent 实际执行的工具序列**：

~~~
Skill → Read → Bash → Bash → Glob → Bash → Glob → Bash ×3 → Grep → Read → Bash ×2 → AskUserQuestion
~~~

**产出的东西**：
- 没有产出文件（这是一个纯分析型 skill）
- 最终回复中定位了根因：response.data 为 null（当 API 返回 204 时）

**关键行为**：agent 经历了 11 次 Bash 调用和 1 次 Grep——大量的搜索和验证步骤，符合 skill 教的"系统性调查"方法。最后用 AskUserQuestion 确认修复方向。

### frontend-design（UI 设计方向建议）

anthropics 官方的视觉设计指导。

**agent 实际执行的工具序列**：Skill → Read（简单场景，工具调用少）

**产出的东西**：纯文字回复（配色和字体方向建议），无文件产出。

---

## 二、六个评测工具的能力与能力边界

### plugin-eval

**它能做什么**：
- 读 SKILL.md 文件、估算 token 数（字符数除以 4）
- 检查 frontmatter 格式（name 和 description 是否存在）
- 检查相对链接是否有断链
- 对比 token 数和 Codex 基线常量，给出预算等级
- 对 skill 目录里的脚本做代码质量检查（复杂度、超长行、缺测试）

**它怎么打分**：
不跑模型。每个检查项有严重度（error=14 分/warning=6 分/info=1 分）和状态系数（fail=1.0/warn=0.75/info=0.25），扣分公式是 score = 100 - Σ(权重×系数)。

**它的能力边界**：

| 能看到 | 看不到 |
|---|---|
| 文件的结构合规性 | skill 是否会被触发 |
| token 预算是否超过阈值 | agent 是否真的执行了 skill 里的脚本 |
| 引用链接是否断裂 | 产物文件是否正确生成 |
| 脚本代码的静态质量 | 多轮对话中的行为 |
| | 与没有 skill 时的基线差异 |

**实测证据**：us-breakdown 的两个 CLI 脚本有 bug（解析器漏了一条 AC、校验器没剥 BOM），plugin-eval 给了 95/A——它检查了脚本代码质量但没发现这两个 bug，因为它不执行脚本。

**实测证据**：product-manager 的 SKILL.md 里描述了多 agent 协作流程，plugin-eval 只看到"正文太长"（1663 tokens），给扣了 14 分。它不知道这段正文实际上引导 agent 完成了正确的行为。

### skill-up

**它能做什么**：
- 起 Claude Code 进程执行任务
- expect 预检（零成本检查：文件是否存在、内容是否包含关键词）
- rule_based 判分（声明式规则：output_contains/output_matches/tool_called）
- script 判分（运行外部脚本，exit 0 = PASS）
- agent_judge 判分（LLM 裁判，严格 JSON 输出 + 重试一次 + pass_threshold 0.7）
- 多轮对话（SessionResumer 续接会话）
- 产出 Anthropic 兼容的 grading.json

**它怎么打分**：
expect 先跑（免费，失败短路跳过 judge）；然后 judge 跑（按声明的规则或 LLM 裁判）。pass_rate = 通过数/总数。

**它的能力边界**：

| 能看到 | 看不到 |
|---|---|
| 最终消息文本是否包含指定关键词 | 与没有 skill 时的基线差异（默认不跑对照组） |
| 期望的文件是否存在 | agent 使用了哪些工具（除非写 tool_called 规则） |
| 文件内容是否包含子串 | agent 是否遵循了 skill 规定的完整工作流 |
| 工具是否被调用（tool_called 规则） | 多个工具的调用顺序 |
| LLM 裁判的主观评分 | 客观的产物结构校验（如 JSON schema 验证） |

**实测证据**：root-cause-analysis 的 agent 正确定位了根因，但最终消息里用了"undefined"而不是"null"——skill-up 的 output_contains 规则检查"null"，判定 FAIL。同一个 skill 在 agentut（DeepSeek 模型）上 PASS，因为 DeepSeek 恰好用了"null"这个词。

**实测证据**：tdd-guide 的评测中，我在 judge.success 里写了 output_contains "AC1"（这是另一个 skill 的关键词）。skill-up 不会提示"这个关键词跟当前 skill 无关"，直接判 FAIL。

### agentut

**它能做什么**：
- 起 opencode 进程（DeepSeek 模型）执行任务
- 7 种断言：should_call_tool（最强，能验工具名/参数/状态）、should_not_call_tool、should_produce_file、file_content_contains、response_contains、exec_command、judged_by
- Matcher 五档匹配：equals/contains/containsOneOf/regex/oneOf
- 多场景支持（正例+负例）
- 概率判定（runs/min_pass）
- mock 工具调用（MockRule）

**它怎么打分**：
断言分 = round(通过断言数/总断言数 × 100)。场景分按 priority 加权平均。

**它的能力边界**：

| 能看到 | 看不到 |
|---|---|
| skill 是否被调用（should_call_tool） | 与没有 skill 时的基线差异 |
| 产物文件是否存在 | 工具调用的完整序列（只查单次调用） |
| 文件/回复是否包含指定子串 | agent 是否遵循了多步骤工作流 |
| 负例（不相关问题不触发） | 产物内容的结构正确性 |
| | CLI 脚本是否真的被执行 |

**实测证据**：tdd-guide 的 agent 写了测试文件，但文件名不是精确的 src/utils.test.js——agentut 的 should_produce_file 是精确匹配（不是 glob），直接判 FAIL 扣了 25 分。

**实测证据**：us-breakdown 的 agent 用 Bash 执行了两个 CLI 脚本，但 agentut 没有断言能验证这一点（should_call_tool 只查工具名和参数匹配，没有 Bash command 的子串匹配）。

### skilljack-evals

**理论能力**（从文档和源码分析）：
- 三维评分：discovery（是否触发）/ adherence（是否遵循指令）/ output（输出质量）
- LLM 裁判评分
- 多次运行统计（CI 模式）
- 确定性检查 + LLM 裁判混合

**实际能力边界**：本机无法运行。

它的 claude-sdk runner 直连 Anthropic API，不走本地 Claude Code 登录态。没有 ANTHROPIC_API_KEY 时：
- 不报错、不提示缺 key
- 静默输出空结果（output=""、tokens=0、cost=$0）
- 空结果被算作评测 FAIL

这比"不能运行"更糟糕——**你不知道它没跑**。

### skillgrade

**理论能力**（从文档分析）：
- 三档预设：smoke（5 次）/ reliable（15 次）/ regression（30 次）
- 确定性 grader（脚本输出 JSON {score, checks}）
- LLM rubric grader
- Docker 或本地 provider
- 多 agent 支持（gemini/claude/codex/opencode/command/acp）

**实际能力边界**：本机无法运行。

六种 agent 在本机全部失败：
- gemini：需要 GEMINI_API_KEY
- claude：需要 ANTHROPIC_API_KEY
- codex：需要 OPENAI_API_KEY
- opencode：能启动但 agent 对接失败（1 秒内全部 FAIL）
- command：Windows 上 bash 包装脚本不兼容
- acp：需要 ACP 环境

### comet

不是独立评测 CLI，是一个 63MB 的完整 agent 平台（含 UI、数据库、CI 集成）。不适合拿来对比评测。

---

## 三、各工具在同一个 Skill 上看到了什么、漏了什么

以 us-breakdown（最复杂的被测 skill）为例：

| 维度 | plugin-eval | skill-up | agentut | skilljack | skillgrade |
|---|---|---|---|---|---|
| skill 是否被触发 | 看不到 | 看不到（需配 tool_called 规则） | **能看到** | 能看到（但没跑起来） | 能看到（但没跑起来） |
| us_parser.mjs 是否被执行 | 看不到 | 看不到 | 看不到 | — | — |
| validate_breakdown.mjs 是否被执行 | 看不到 | 看不到 | 看不到 | — | — |
| validate 是否返回 exit 0 | 看不到 | 能设 script judge 验 | 看不到 | — | — |
| breakdown.json 是否存在 | 看不到 | **能看到**（files_exist） | **能看到**（should_produce_file） | — | — |
| breakdown.json 包含 AC1 | 看不到 | **能看到**（file_contains） | **能看到**（file_content_contains） | — | — |
| 任务的 estimate_days 是否合规 | 看不到 | 看不到（子串匹配验不了数值范围） | 看不到 | — | — |
| 与不装 skill 的基线差异 | 看不到 | 看不到（默认不跑对照组） | 看不到 | — | — |
| SKILL.md 里引用的脚本代码质量 | **能看到**（静态分析） | 看不到 | 看不到 | — | — |
| SKILL.md 的 token 预算 | **能看到** | 看不到 | 看不到 | — | — |

以 root-cause-analysis（纯分析型 skill）为例：

| 维度 | plugin-eval | skill-up | agentut |
|---|---|---|---|
| skill 是否被触发 | 看不到 | 看不到 | **能看到** |
| agent 是否做了系统性调查 | 看不到 | 看不到 | 看不到 |
| agent 是否问了用户 | 看不到 | 看不到 | 看不到 |
| 最终回复是否含"null" | 看不到 | **能看到**（但 Claude 用了"undefined"，FAIL） | **能看到**（DeepSeek 恰好用"null"，PASS） |
| 根因定位是否正确 | 看不到 | 看不到 | 看不到 |
| 调试方法论是否被遵循 | 看不到 | 看不到 | 看不到 |

---

## 四、能力边界的根本原因

### 1. 静态工具（plugin-eval）的边界源于"不执行"

plugin-eval 只读文件。它能告诉你"这个 skill 写得规范吗"，但不能告诉你"这个 skill 能用吗"。这不是缺陷而是定位——它是一个结构检查器，不是行为测试器。

### 2. 行为工具（skill-up / agentut）的边界源于"子串匹配 + 单模型"

skill-up 和 agentut 都通过"起一个模型跑任务，然后检查最终输出"来评测。这带来三个根本限制：

- **子串匹配脆弱**：agent 用了"undefined"而不是"null"就 FAIL，尽管语义相同
- **单模型偏差**：同一个断言关键词在 Claude 上 FAIL、在 DeepSeek 上 PASS
- **看不到过程**：只验最终输出，不知道中间经历了什么工具调用

### 3. 对照组的缺失

除了我们自建的 cc-eval，没有任何一个开源工具默认提供"装了 skill vs 不装 skill"的对照组。这意味着它们**无法回答"这个 skill 有没有增量价值"**——只能回答"agent 在有 skill 的情况下做对了没有"，但不能回答"没有 skill 时是不是也能做对"。

### 4. 流程验证的缺失

us-breakdown 规定了六步工作流（其中两步是"运行脚本"），但没有任何一个开源工具能验证"agent 是否真的执行了这些步骤、按什么顺序执行"。agentut 的 should_call_tool 能验单次工具调用，但看不到完整的调用序列。

### 5. 基础设施脆弱性

- skilljack-evals 在没有 API key 时**静默失败**——比报错更危险
- skillgrade 的六种 agent 在本机全部不兼容
- 我们自己的实验中，PowerShell 编码 bug 导致 57 个文件损坏，plugin-eval 对全部损坏文件给了 F——**评测工具不会检测输入是否合法**

---

## 五、能力矩阵总结

| 能力 | plugin-eval | skill-up | agentut | skilljack | skillgrade |
|---|---|---|---|---|---|
| 结构合规检查 | **有** | 无 | 无 | 无 | 无 |
| token 预算审计 | **有** | 无 | 无 | 无 | 无 |
| 断链检查 | **有** | 无 | 无 | 无 | 无 |
| 脚本代码静态质量 | **有** | 无 | 无 | 无 | 无 |
| 触发验证 | 无 | 可配 | **有** | 有（跑不了） | 有（跑不了） |
| 最终输出文本匹配 | 无 | **有** | **有** | — | — |
| 产物文件存在性 | 无 | **有** | **有** | — | — |
| 产物内容子串匹配 | 无 | **有** | **有** | — | — |
| 工具调用验证 | 无 | 可配 | **有**（单次） | — | — |
| 工具调用序列验证 | 无 | 无 | 无 | — | — |
| 多轮对话 | 无 | **有** | **有** | 无 | 无 |
| 对照组（lift） | 无 | 可选 | 无 | 无 | 无 |
| LLM 裁判 | 无 | **有** | **有** | 有 | 有 |
| 多次运行统计 | 无 | 无 | **有** | 有 | 有 |
| 本机可运行 | **有** | **有** | **有** | 无 | 无 |

---

## 六、结论

**没有任何一个评测工具能独立覆盖 skill 评测的全部维度。**

plugin-eval 覆盖"写得对不对"（结构/预算/断链），但不碰行为。
skill-up 和 agentut 覆盖"做了没有"（输出/产物），但看不到过程和增量。
skilljack 和 skillgrade 设计上最全面，但在没有对应 API key 的环境下完全无法使用。

如果要覆盖全部维度，至少需要组合两个工具：plugin-eval（静态）+ skill-up 或 agentut（行为）。即使组合，仍然缺失的是：工具调用序列验证、CLI 执行验证、对照组（lift）、跨模型一致性。
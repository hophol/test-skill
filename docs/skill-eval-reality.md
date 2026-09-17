# Skill 评测实录：被测 Skill、评测方式、打分是否真实

> 9 个真实 skill / 5 种评测工具 / 全部本机真跑

## 一、被测 Skill：是什么、干了什么、产出了什么

### 1. us-breakdown（前端 US 拆解，含 CLI 工具）

是什么：一个带 2 个真实 CLI 脚本的复杂 skill。给定一个用户故事（US）markdown 文件，产出结构化的任务拆解。

工作流（SKILL.md 规定的 6 步）：
1. 读 US 文件
2. 运行 scripts/us_parser.mjs 拿到结构化验收标准（不许肉眼解析）
3. 按 references/decomposition-rules.md 的模板为每条 AC 生成任务
4. 估点遵循 references/estimation.md（单任务不超过 1 天）
5. 产出 breakdown.json + tasks.md 两个文件
6. 运行 scripts/validate_breakdown.mjs 校验（失败就修产物再跑）

评测时产出了什么：
- agent 按流程走了全部 6 步
- 真的用 Bash 调了 us_parser.mjs 和 validate_breakdown.mjs（cc-eval 的 must_call_tool 断言验证）
- 产出了 breakdown.json（包含全部 3 条 AC、每个任务有 id/ac/title/estimate_days/test_hint）
- 产出了 tasks.md（人类可读任务清单）
- 第 2 轮 PM 补了 AC4，agent 重新拆解并重跑了 validator

### 2. product-manager（PM 全流程，多 agent 协作）

是什么：从 SkillsMP 找到的 PM 全流程 skill。正常需要 5 个子 agent（strategist/prd-writer/story-writer/sprint-planner/pm-reviewer）协作。测试时只装了 SKILL.md，没装子 agent 文件（模拟从 marketplace 裸装）。

评测时产出了什么：
- agent 即兴用内置 Agent 工具模拟了多 agent 协作（没有真正的子 agent 文件也能工作）
- 产出了 _workspace/03_user_stories.md（标准格式 user stories，含 As a/I want/AC）
- 产出格式正确，包含 Given-When-Then 验收标准

### 3. tdd-guide（TDD 测试编写指南）

是什么：403 行的详细 TDD 工作流指南，覆盖 Jest/Pytest/JUnit/Vitest/Mocha。

评测时产出了什么：
- agent 读了 src/utils.js 源码
- 用 Bash 跑了 npm test 验证测试通过
- 产出了测试文件（包含 formatDate 多种用例：ISO 日期、补零、空值等）
- agentut 期望文件名为 src/utils.test.js（精确匹配），agent 可能写成了别的名字，因此 agentut 扣了分

### 4. root-cause-analysis（根因分析调试）

是什么：174 行的结构化调试方法论。核心原则：永远不要修症状，必须找到并修复根因。使用 Five Whys 方法。

评测时产出了什么：
- agent 读了 src/userList.js 源码，用 Bash/Grep 多轮搜索
- 用 AskUserQuestion 向用户确认修复方向（skill 教的行为之一）
- 回复中正确定位了 null 和 204（API 返回空内容时的边界问题）

### 5. frontend-design（UI 设计方向建议）

是什么：anthropics 官方的视觉设计指导 skill（58 行）。不产出文件，只输出文字建议。

评测时产出了什么：给出了咖啡品牌官网的配色和字体方向建议。

---

## 二、每个评测工具是怎么评的

### plugin-eval

评测方式：不跑模型。读 SKILL.md，用 ceil(字符数/4) 估 token，对比 Codex 基线常量，检查结构规则。
扣分公式：score = 100 - Sigma(严重度权重 x 状态系数)。error/fail 扣 14 分，warning/warn 扣 4.5 分。

给分结果：
- us-breakdown: 95/A（deferred 950 偏重，扣 4.5 warning）
- product-manager: 53/F（trigger 186 + invoke 1663 双超预算，扣 28 error + 4.5 warning）
- tdd-guide: 77/C（invoke 3393 超预算，扣 14 error + 4.5 warning）
- root-cause-analysis: 67/D（trigger 155 + invoke 1352 双超预算，扣 28 error）
- frontend-design: 67/D（invoke 2359 + deferred 2588 超预算，扣 28 error + 4.5 warning）

### cc-eval 路由（早停）

评测方式：起 claude，每 400ms 读事件流，看到 Skill 调用就杀进程树。
结果：9/9 全触发（4-23 秒，0 美元）。

### cc-eval 行为（两臂）

评测方式：同一 prompt 跑两遍（装/不装 skill），按轮断言（工具调用、产物文件、内容子串）。
lift = with_skill 通过率 - without_skill 通过率。
结果：5 个跑了全量的 skill 全部 lift=1。

### agentut

评测方式：YAML 定义场景，起 opencode（DeepSeek），断言 7 种（should_call_tool 最强）。
断言分 = round(通过数/总数 x 100)。

结果：
- us-breakdown: 100（4 个断言全过）
- ping-check: 100（2 个场景全过）
- tdd-guide: 75（should_produce_file 精确匹配失败——agent 写的文件名不是 src/utils.test.js）
- root-cause-analysis: 100（skill 调用过、回复含 null）

### skilljack-evals

评测方式：需要 ANTHROPIC_API_KEY。本机没有，静默输出空结果，空结果算 FAIL。
不提示缺 key、不报错——比不能运行更糟糕，因为你不知道它没跑。

---

## 三、打分是否真实反映了被测 skill 的情况

### 逐 skill 判定

#### us-breakdown
- plugin-eval 说 95/A："结构好"
- 行为测试说 PASS lift=1："确实有用"
- 真实情况：结构确实好，但 CLI 脚本有 2 个 bug（冒烟时抓到：漏 AC、没剥 BOM），评测前我们修好了
- 判定：plugin-eval 的 95/A 没看到 bug。行为测试的 PASS 是修好后跑的。两个都对，但都不完整。

#### product-manager
- plugin-eval 说 53/F："写得太差"
- 行为测试说 PASS lift=1："确实有用"
- 真实情况：skill 正文确实很长（1663 tokens），但 agent 即兴模拟多 agent 后产出了正确格式。没有 skill 时基线连格式都不对。
- 判定：plugin-eval 的 F 级不反映有用性。lift=1 是真实的（产物确实比基线好）。

#### tdd-guide
- plugin-eval 说 77/C："invoke 太长"
- 行为测试说 PASS lift=1。agentut 说 75。
- 真实情况：skill 确实长（403 行），但 TDD 指南内容丰富是有意义的。agent 读了 skill 后走了 TDD 流程。没有 skill 时也能写测试，但没走 TDD 流程。
- 判定：77/C 只反映"写得长"，不反映"教得好"。lift=1 的来源是"流程合规"，不是"产物质量差距"。agentut 的 75 是精确匹配假阴性（文件名不一致，不是内容有问题）。

#### root-cause-analysis
- plugin-eval 说 67/D："双超预算"
- 行为测试说 PASS lift=1。agentut 说 100。
- 真实情况：skill 确实 1352 tokens，但调试方法论需要这个篇幅。agent 加载后确实用了 AskUserQuestion 确认方向（skill 教的行为）。回复正确定位了问题。
- 判定：67/D 与实际效果无关。agentut 的 100 更接近真实，但也只验了子串。

#### frontend-design
- plugin-eval 说 67/D："超预算"
- 行为测试说 PASS lift=1。
- 真实情况：anthropics 官方 skill，正文 2359 tokens 是故意的（详细的设计指导）。
- 判定：67/D 是对官方 skill 的误判——不是"写得太差"，是"写得详细"。

### 总结

| 工具 | 打分真实反映了 | 打分没有反映 |
|---|---|---|
| plugin-eval | 文件结构合规性；token 预算；断链 | skill 是否能工作；产物质量；与基线的差异 |
| cc-eval 路由 | description 写得够不够好 | 触发后的行为质量 |
| cc-eval 行为 | skill 是否有增量价值（lift）；流程是否被遵循 | 产物质量的深层校验；边界输入的行为 |
| agentut | skill 是否被触发；产物是否存在 | 文件名变化（假阴性）；流程合规；与基线差异 |
| skilljack | 无法评判（本机无法运行） | — |

最终结论：

1. plugin-eval 的分数与 skill 的实际效用不相关。53/F 的能用，95/A 的有 bug，67/D 的是官方作品。

2. cc-eval 的 lift 是目前唯一能回答"装了比不装好多少"的指标。但它的判据主要是"流程合规"和"产物存在"，对"产物质量差距"的分辨力有限。

3. agentut 最快最便宜，但精确匹配会产生假阴性。tdd-guide 因为文件名不同扣了 25 分，这不是 skill 的问题。

4. skilljack-evals 在没有 API key 的环境下会静默失败并给出误导性的 FAIL 结果。这比不能运行更糟糕。

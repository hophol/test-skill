# Agent Skill 评测能力调研：完整报告

> 周期：2026-09-13 至 2026-09-17
> 被测 skill：90 个（60 个 openai/plugins + 30 个本地多来源）
> 评测工具：6 个开源（plugin-eval / skill-up / agentut / skilljack-evals / skillgrade / comet）+ 1 个自建（cc-eval）
> 方法：V1 结果验证 → V2 过程+结果验证（引入区分度用例、降级测试、细粒度验证条件）
> 全部数据为本机真实运行，含失败和 infra bug 的完整记录

---

## 一、调研目标

回答三个问题：
1. 现有开源评测工具的能力是什么、边界在哪里？
2. 用真实 skill 跑这些工具，结果是否可信？
3. 评测方法论本身应该怎么设计？

---

## 二、被测 Skill 语料

| 来源 | 数量 | 典型 |
|---|---|---|
| openai/plugins | 60 | swiftpm-macos / test-triage / adobe 系列 / figma 系列 / boltz 系列 |
| anthropics/skills | 5 | frontend-design / canvas-design / mcp-builder / brand-guidelines / doc-coauthoring |
| DSH 仓 | 11 | dsh-code-review / dsh-prose-standard / dsh-pre-push-checks 等 |
| skill-test-kit | 6 | fe-req-analysis / fe-dev-design / fe-test-design / web-artifacts-builder / webapp-testing |
| SkillsMP | 7 | product-manager / tdd-guide / root-cause-analysis / team-qa / repo-health / browser-to-api / requesting-code-review |
| 自建 | 1 | us-breakdown（含 2 个 CLI 脚本 + 验证环 + 多轮修订） |

其中 5 个 skill 跑了完整的两臂行为评测（with_skill vs without_skill），
2 个 skill 跑了 V2 方法论的区分度用例和降级测试。

---

## 三、6 个开源评测工具的能力与边界

### 3.1 运行状况

| 工具 | 能否运行 | 原因 |
|---|---|---|
| plugin-eval (OpenAI) | 能 | 纯静态分析，不需要模型 |
| skill-up (alibaba) | 能 | 用 Claude Code 本地登录态 |
| agentut | 能 | 用 opencode + DeepSeek |
| skilljack-evals | 不能 | 需要 ANTHROPIC_API_KEY，没有时静默输出空结果算 FAIL |
| skillgrade | 不能 | 6 种 agent 全不兼容本机环境 |
| comet | 不适用 | 不是独立评测 CLI，是 63MB 完整 agent 平台 |

### 3.2 plugin-eval 在 90 个 skill 上的能力

它是唯一能在 90 个 skill 上全量运行的工具（免费，每个 <1 秒）。

**它能看到的**：

| 能力 | 证据 |
|---|---|
| token 预算全貌 | 90 个 skill 的 trigger（avg 82）/invoke（avg 2245）/deferred 全部量化 |
| 极端异常值 | adobe-retouch-portraits invoke=10151（操作手册塞进 SKILL.md） |
| 等级分布 | A:15 / B:20 / C:34 / D:16 / F:5 |
| 断链检查 | browser-to-api 的 broken-relative-links（所有行为测试看不到） |
| 脚本静态质量 | 复杂度 / 超长行 / 缺配套测试 |

**它看不到的**：

| 盲区 | 证据 |
|---|---|
| skill 是否能工作 | 53/F 的 product-manager 实际能工作（lift=1）；95/A 的 us-breakdown CLI 有 bug |
| 是否会被触发 | 不跑模型 |
| agent 是否遵循工作流 | 不跑模型 |
| 输入是否合法 | 57 个损坏文件全给 F，不提示输入有问题 |

### 3.3 skill-up 的能力与边界

**能看到的**：最终消息文本的关键词、产物文件存在性、文件内容子串、多轮对话。

**看不到的**：
- 与没有 skill 的基线差异（对照组默认关闭）
- 工具调用的完整序列
- CLI 脚本是否真的被执行

**实测暴露的问题**：

| 问题 | 证据 |
|---|---|
| 子串匹配跨模型不稳定 | root-cause-analysis：Claude 用"undefined"→FAIL；DeepSeek 恰好用"null"→PASS |
| judge 规则写错不报错 | 我在 tdd-guide 的 judge 里写了另一个 skill 的关键词（AC1），skill-up 不会提示 |
| 超时和失败不区分 | frontend-design 首跑 240s 超时判 ERROR，放宽到 600s 后 PASS |

### 3.4 agentut 的能力与边界

**能看到的**：skill 是否被调用（should_call_tool）、产物文件是否存在、内容是否含关键词、负例（不相关问题不触发）。

**看不到的**：
- 工具调用的序列（只查单次调用）
- Bash 命令的内容（无法验证 CLI 是否真的被执行）
- 与基线的差异
- 产物内容的结构正确性

**实测暴露的问题**：

| 问题 | 证据 |
|---|---|
| 精确匹配假阴性 | tdd-guide 的 agent 写了测试但文件名不是 src/utils.test.js，扣 25 分 |
| 看不到 CLI 执行 | us-breakdown 用 Bash 跑了 2 个脚本，agentut 无法验证这一点 |

### 3.5 skilljack-evals / skillgrade / comet

skilljack-evals：设计上最全面（三维评分 discovery/adherence/output + LLM 裁判 + 多次运行统计），但需要 ANTHROPIC_API_KEY。没有 key 时**不报错、不提示、静默输出空结果算 FAIL**——比不能运行更危险。

skillgrade：六种 agent（gemini/claude/codex/opencode/command/acp）在本机全部失败。cli 安装了但无法对接任何本地模型。

comet：不是评测 CLI，是完整平台。

---

## 四、V1 评测结果（结果验证）

### 4.1 两臂行为测试（5 个 skill）

| Skill | with_skill | without_skill | lift | with_skill 做了什么 |
|---|---|---|---|---|
| us-breakdown | PASS 160s $0.48 | FAIL 241s $0.59 | 1 | 跑了 2 个 CLI、产出 breakdown.json + tasks.md、validator 通过 |
| product-manager | PASS 479s $1.31 | FAIL 284s $0.90 | 1 | 即兴用内置 Agent 工具模拟多角色协作、产出 user stories |
| tdd-guide | PASS 191s $0.79 | FAIL 240s $0.68 | 1 | 读了源码、跑了 npm test、产出测试文件、用了 AskUserQuestion |
| root-cause-analysis | PASS 145s $0.47 | FAIL | 1 | 读了源码、11 次 Bash 搜索、用 AskUserQuestion 确认方向 |
| frontend-design | PASS 108s $0.20 | FAIL 44s $0.10 | 1 | 给出配色和字体方向建议 |

### 4.2 V1 的局限（为什么需要 V2）

V1 的断言主要是"结果验证"（产物存在 + 内容含关键词）。两个关键盲区：

1. **用例没有区分度**：tdd-guide 的基线也能写测试。lift=1 来自"流程合规"（must_call_skill 失败），不是"质量差距"。简单用例上 Skill 的贡献在效率不在正确性。

2. **不测过程**：agent 蒙对了（没走规定流程但结果碰巧对）会判 PASS。agent 遇到工具故障选择停下来（可靠行为）会判 FAIL（任务没完成）。

---

## 五、V2 评测结果（过程+结果验证）

### 5.1 方法论设计原则（6 条）

来自 Richard Wang 的文章 + 本仓实测教训：

1. **用例必须有区分度**——命中 Skill 的介入决策点，不能是模型凭常识就能做对的
2. **验证条件拆细**——5+ 条，分结果/过程/格式三类
3. **过程 vs 结果分开**——蒙对了但没走流程 = 判失败；工具挂了停下来 = 判通过
4. **基线物理隔离**——独立目录，skill 文件不可见
5. **从工具调用序列判定**——不解析总结文本
6. **验证条件不创造 Skill 没承诺的标准**

### 5.2 区分度用例实测

构造了一个非标准格式的 US（5 条 AC，其中 1 条以"此外"引出、无编号前缀）。

**结果**：agent 正确跑了 parser 脚本，但 **parser 的关键词过滤器漏掉了"此外"开头的那条 AC**——拆解结果只有 4 条而不是 5 条。

**旧用例为什么看不到**：旧用例（us-login.md）所有 AC 都有显式编号（AC1:/AC2:/AC3:），parser 全部正确提取。换一个非标准格式，bug 就暴露。

**意义**：V2 的区分度用例暴露了 skill 本身的一个 bug——如果上线，这条验收标准对应的任务会被遗漏。

### 5.3 降级测试实测

把 parser 脚本替换成报错版本（模拟"工具不可用"）。

**agent 的实际行为**：
1. 尝试跑 parser → 失败（exit 1）
2. **读了 parser 源码**理解输出 schema
3. **手工按 schema 推演**了结果
4. 照样产出了 breakdown.json（甚至过了 validator）
5. 在回复中主动说明："解析器降级...改为人工解析"

**V1 会怎么判**：breakdown.json 存在且内容正确 → PASS
**V2 的判定**：must_not_write_file_pattern 失败 → **FAIL**

**为什么 V2 判 FAIL**：工具不可用时应该停下来而不是绕过。agent 虽然透明地说明了降级，但行为不可靠——下次遇到不同的 US，手工推演可能引入 parser 不会犯的错误。

### 5.4 V2 的两个发现都是旧方法完全看不到的

| 发现 | V1（结果验证） | V2（过程+结果验证） |
|---|---|---|
| parser 漏 AC | 看不到（旧用例全是显式编号） | **抓到了**（非标准格式 US 触发） |
| 工具挂了不停下来 | 看不到（产物格式正确就 PASS） | **抓到了**（must_not_write 判 FAIL） |

---

## 六、评测基础设施的可靠性问题

本次调研中遇到的评测基础设施 bug（全部真实发生并记录）：

| 问题 | 影响 | 发现方式 |
|---|---|---|
| PowerShell 编码 bug | 57 个 SKILL.md 变成字节值文本，plugin-eval 全给 F | 错误结论"69% 不合格"；修复后实际 F 只有 5.6% |
| skill-up judge 规则写错 | 我在 tdd-guide 里写了 AC1（另一个 skill 的关键词），skill-up 不报错 | 正常 skill 被判 FAIL 50% |
| agentut 精确匹配 | agent 写的文件名不是 src/utils.test.js 就扣分 | 假阴性（skill 本身没问题） |
| skilljack 缺 API key | 静默输出空结果算 FAIL | 看起来像 skill 有问题，实际是工具没跑 |
| cc-eval 权限问题 | 不加 --dangerously-skip-permissions 时 CLI 被 Bash 权限拦截 | agent 读源码手工推演（结果对但过程违规） |

**结论**：评测工具本身也需要被评测。任何评测结果在确认基础设施正常之前都不应被信任。

---

## 七、核心发现总结

### 7.1 没有一个工具能独立给出可信判定

plugin-eval 只看结构（分数与有用性不相关）。skill-up 和 agentut 只看结果（子串匹配脆弱且跨模型不稳定）。skilljack/skillgrade 无法在本机运行。V2 的过程验证能力（must_call_tool / must_not_write_file_pattern）目前只存在于自建工具中。

### 7.2 行为评测无法在 90 个 skill 的规模上运行

plugin-eval 能 90 秒免费跑完 90 个。skill-up / agentut 每个用例需要手写 10-40 行 YAML + 60-240 秒 + $0.02-1.30。90 个 = 1.5-6 小时 + $2-117 + 不可能手写完的配置。

### 7.3 评测是层层嵌套的，任何一层失败上层全部作废

用例没区分度 → 验证条件白设计。验证条件没拆细 → 退步了不知道哪里退步。基线没隔离 → 差异说不清来源。评分不可信 → 前面全白做。

### 7.4 过程验证是区分"碰巧对了"和"可靠地对"的唯一手段

蒙对了但没走流程 = 应该判失败（下次遇到不是常识的会错）。工具挂了选择停下来 = 应该判通过（行为可靠）。这两个判定只有过程验证（检查工具调用序列和行为模式）才能做到。

### 7.5 评测条件本身也需要被评测

验证条件可能创造 Skill 没承诺的标准（如要求中文名但 SKILL.md 说"用最通用的指代"）。评测用例可能命中不了 Skill 的介入决策点。评分 Agent 可能假阳性（基线 token 消耗低但通过率高 = 可疑）。

---

## 八、方向建议

### 已验证有效的做法

1. **分层评测**：静态（plugin-eval，秒级免费）→ 路由（早停，秒级）→ 行为（两臂，分钟级）→ 过程验证（V2 方法论）
2. **对照组（lift）**：唯一能回答"装了比不装好多少"
3. **区分度用例**：必须选"命中 Skill 介入决策点"的难用例
4. **降级测试**：工具不可用时的行为是可靠性的关键指标
5. **过程验证**：从工具调用序列判定，不解析总结文本

### 不建议做的

1. 不要只依赖静态分数（与有用性不相关）
2. 不要只看结果不看过程（会漏掉"蒙对了"和"工具被绕过"）
3. 不要在评测条件里创造 Skill 没承诺的标准
4. 不要同时改 Skill 和切换模型（说不清差异来源）
5. 不要信任评测结果除非确认基础设施正常

---

## 附录

### A. 评测工具对比矩阵

| 能力 | plugin-eval | skill-up | agentut | skilljack | skillgrade | comet | cc-eval |
|---|---|---|---|---|---|---|---|
| 能跑 90 个 | 是(90s/免费) | 否(太贵) | 否(配置多) | 否(缺key) | 否(不兼容) | 否(是平台) | 否(太贵) |
| token 预算审计 | 有 | 无 | 无 | 无 | 无 | 无 | 无 |
| 断链检查 | 有 | 无 | 无 | 无 | 无 | 无 | 无 |
| 路由验证(早停) | 无 | 无 | 有 | - | - | - | 有(4-11s) |
| 产物存在性 | 无 | 有 | 有 | - | - | - | 有(glob) |
| 产物子串匹配 | 无 | 有 | 有 | - | - | - | 有 |
| 工具调用验证 | 无 | 可配 | 有(单次) | - | - | - | 有(command_contains) |
| 工具调用序列 | 无 | 无 | 无 | - | - | - | 无 |
| 多轮对话 | 无 | 有 | 有 | 无 | 无 | - | 有(--resume) |
| 对照组(lift) | 无 | 可选(默认关) | 无 | 无 | 无 | 无 | 有(默认两臂) |
| 过程验证(V2) | 无 | 无 | 无 | - | - | - | 有(must_not_write) |
| 降级测试 | 无 | 无 | 无 | - | - | - | 有 |
| LLM 裁判 | 无 | 有 | 有 | 有 | 有 | 有 | 无 |
| 输入合法性检测 | 无 | 无 | 无 | - | - | - | oracle gate |

### B. 本仓产出文件清单

| 文件 | 内容 |
|---|---|
| docs/research.md | 12+ 开源项目调研 |
| docs/three-tools-report.md | 三方工具上手简版 |
| docs/three-tools-report-v2.md | 逻辑篇：公式级解析 + 数值验证 |
| docs/capability-structures-report.md | 结构篇：模块/配置/类型/产物/扩展点 |
| docs/eval-acceleration.md | 加速策略（路由早停 600s→5.1s） |
| docs/comparative-data.md | 同一批 skill × 多工具的对比矩阵 |
| docs/opensource-tools-results.md | 开源工具评测结果（含不能运行的 3 个） |
| docs/skill-eval-reality.md | 每个 skill 是什么/怎么评的/分数是否真实 |
| docs/batch-90-skills.md | 90 个 skill 批量静态分析 |
| docs/capability-boundaries.md | 能力边界分析（基于 90 个 skill 规模） |
| docs/eval-methodology-v2.md | V2 方法论设计原则 |
| docs/v2-eval-results.md | V2 实测结果（区分度+降级测试） |
| cc-eval/ | 自建评测 CLI（两臂+多轮+早停+过程验证） |
| CHANGELOG.md | 完整变更记录（P1-P6 / R1-R8 / CC1-CC21） |
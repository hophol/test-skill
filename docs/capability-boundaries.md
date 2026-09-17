# 评测工具的能力与能力边界：基于 90 个真实 Skill 的批量实测

90 个 skill（60 个 openai/plugins + 30 个本地）作为被测语料。6 个评测工具中 3 个能跑，3 个不能。核心问题：这些工具的能力是什么、边界在哪里、在 90 个 skill 的规模下暴露了什么。

## 一、90 个被测 Skill 的构成

| 来源 | 数量 | 典型 |
|---|---|---|
| openai/plugins | 60 | swiftpm / test-triage / adobe / figma / boltz 系列 |
| anthropics/skills | 5 | frontend-design / canvas-design / mcp-builder |
| DSH 仓 | 11 | dsh-code-review / dsh-prose-standard 等 |
| skill-test-kit | 6 | fe-req-analysis / fe-dev-design 等 |
| SkillsMP | 7 | product-manager / tdd-guide / root-cause-analysis 等 |
| 自建 | 1 | us-breakdown（含 CLI + 验证环） |

## 二、plugin-eval 在 90 个 skill 上的能力与边界

plugin-eval 是唯一能在 90 个 skill 上全量跑的工具（免费、不跑模型、每个 <1 秒）。

### 它看到了什么

1. token 预算的全貌分布：8 个 <500 / 36 个 500-2000 / 41 个 2000-5000 / 5 个 >5000。近一半 skill 正文在 2000-5000 区间，超过 plugin-eval 自身 900 的 excessive 阈值。
2. 极端异常值：adobe-retouch-portraits invoke=10151（完整操作手册塞进 SKILL.md）；fe-req-analysis invoke=145（极精简内部 skill）。
3. trigger 成本：最低 28（fe-req-analysis）到最高 208（adobe-design-from-template）。
4. 断链：browser-to-api 有 broken-relative-links，所有行为测试都看不到这个。

### 它看不到什么

1. 90 个 skill 中任何一个是否能工作。product-manager 被打了 53/F 但行为测试显示确实能工作（lift=1）。us-breakdown 拿了 95/A 但 CLI 脚本有 bug。
2. 是否会被触发。plugin-eval 不跑模型。
3. agent 是否遵循工作流。
4. 输入是否合法。PowerShell 编码 bug 导致 57 个文件损坏，plugin-eval 对全部损坏文件给了 F 而不提示输入有问题。

## 三、skill-up 和 agentut 为什么没在 90 个 skill 上跑

成本问题：skill-up 每个用例 60-240 秒 / $0.40-1.30。90 个跑完需 1.5-6 小时 / $36-117。agentut 每个用例 16-60 秒 / $0.02。90 个需 25-90 分钟 / $2。
配置问题：每个 skill 需要手写 10-40 行 YAML。90 个不可能一次完成。

这本身就是能力边界：行为评测工具无法在 90 个 skill 的规模上低成本运行。

在跑过的 5 个 skill 上暴露的边界：

skill-up：子串匹配跨模型不稳定（root-cause-analysis 在 Claude 上 FAIL 因为用了 undefined 不是 null，在 agentut 的 DeepSeek 上 PASS 因为恰好用了 null）。judge 规则写错不报错（我写了错误的关键词 AC1）。

agentut：精确匹配假阴性（tdd-guide 的文件名不是 src/utils.test.js 就 FAIL）。看不到 CLI 执行（us-breakdown 用 Bash 跑了两个脚本，agentut 无法验证）。

## 四、skilljack / skillgrade / comet

skilljack-evals：无法运行。需要 ANTHROPIC_API_KEY。没有 key 时静默输出空结果算 FAIL，不提示缺 key。
skillgrade：无法运行。六种 agent 在本机全部失败。
comet：不是独立评测 CLI，是 63MB 完整平台。

## 五、能力边界的根本原因

1. 静态与行为的鸿沟：plugin-eval 能 90 秒跑完 90 个但只看结构；skill-up/agentut 能看行为但无法规模化。没有工具能同时做到大规模和深评测。
2. 配置成本与规模成反比：plugin-eval 零配置。skill-up/agentut 每个手写 10-40 行。超过 10 个时配置成本不可承受。
3. 子串匹配是所有行为工具的共同弱点：agent 用了不同措辞或不同文件名就假阴性。
4. 没有任何工具验证过程：us-breakdown 规定六步工作流，没有工具能验证 agent 是否按顺序执行了。
5. 没有任何工具默认提供对照组（lift）：无法回答装了这个 skill 比不装好多少。
6. 评测基础设施本身可能出错：57 个损坏文件全给 F、judge 规则写错不报错。

## 六、能力矩阵

| 能力 | plugin-eval | skill-up | agentut | skilljack | skillgrade | comet |
|---|---|---|---|---|---|---|
| 能跑 90 个 | 是(90s/免费) | 否(太贵) | 否(配置多) | 否(缺key) | 否(不兼容) | 否(是平台) |
| 能跑 5 个 | 是 | 是 | 是 | 否 | 否 | 否 |
| token 预算审计 | 有 | 无 | 无 | 无 | 无 | 无 |
| 断链检查 | 有 | 无 | 无 | 无 | 无 | 无 |
| 触发验证 | 无 | 可配 | 有 | - | - | - |
| 产物存在性 | 无 | 有 | 有 | - | - | - |
| 产物子串匹配 | 无 | 有 | 有 | - | - | - |
| 工具调用验证 | 无 | 可配 | 有(单次) | - | - | - |
| 工具调用序列 | 无 | 无 | 无 | - | - | - |
| 多轮对话 | 无 | 有 | 有 | 无 | 无 | - |
| 对照组(lift) | 无 | 可选(默认关) | 无 | 无 | 无 | 无 |
| 输入合法性检测 | 无 | 无 | 无 | - | - | - |

## 七、结论

1. plugin-eval 是唯一能规模化运行的工具，但只覆盖写得对不对。
2. skill-up 和 agentut 无法在 90 个规模上运行，只能小规模行为评测。子串匹配跨模型不稳定。
3. skilljack/skillgrade/comet 在没有 API key 或特定环境下完全无法使用。
4. 没有工具能验证 agent 是否遵循了多步骤工作流。
5. 没有工具默认提供对照组（lift）。
6. 评测基础设施 bug 可以产生大规模误导（57 个损坏文件全给 F）。
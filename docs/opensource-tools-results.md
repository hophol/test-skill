# 开源评测工具对真实 Skill 的评测结果

6 个开源工具 / 5 个真实 skill / 排除自研工具的数据 / 全部本机真实运行

## 工具运行状况

| 工具 | 能跑？ | 原因 |
|---|---|---|
| plugin-eval (OpenAI) | 能 | 纯静态分析，不需要模型 |
| skill-up (alibaba) | 能 | 用 Claude Code 本地登录态 |
| agentut | 能 | 用 opencode + DeepSeek |
| skilljack-evals | 不能 | 需要 ANTHROPIC_API_KEY，静默输出空结果算 FAIL |
| skillgrade | 不能 | 6 种 agent 全不兼容本机环境 |
| comet | 不能 | 不是独立评测 CLI，是 63MB 平台 |

## 三个能跑的工具的评测结果

### us-breakdown（US 拆解，含 CLI）

| 工具 | 评测方式 | 结果 | 耗时 |
|---|---|---|---|
| plugin-eval | 静态分析 | 95/A | <1s |
| skill-up | 行为：起 claude，验消息含 AC1 | PASS 100% | 102s |
| agentut | 行为：起 opencode，验工具+产物 | 100/100 | 16s |

### tdd-guide（TDD 测试编写）

| 工具 | 评测方式 | 结果 | 耗时 | 失败原因 |
|---|---|---|---|---|
| plugin-eval | 静态 | 77/C | <1s | invoke 3393 超预算 |
| skill-up | 行为：验消息含关键词 | FAIL 50% | 237s | judge 规则里写了 AC1（us-breakdown 的词，不是 tdd 的）——配置错误 |
| agentut | 行为：验工具+产物 | 75/100 | ~60s | should_produce_file 精确匹配失败（文件名不同） |

### root-cause-analysis（根因分析）

| 工具 | 评测方式 | 结果 | 耗时 | 失败原因 |
|---|---|---|---|---|
| plugin-eval | 静态 | 67/D | <1s | 双超预算 |
| skill-up | 行为：验消息含 null | FAIL 0% | 64s | agent 找到了根因但最终消息没写 null 这个词（用了别的表述） |
| agentut | 行为：验回复含 null | 100/100 | ~40s | DeepSeek 的回复恰好包含 null |

### frontend-design（UI 设计）

| 工具 | 结果 | 耗时 | 说明 |
|---|---|---|---|
| plugin-eval | 67/D | <1s | anthropics 官方 skill，超预算是故意的 |
| skill-up | PASS | 195s | 首跑 240s 超时 |

### product-manager（PM 全流程）

| 工具 | 结果 | 说明 |
|---|---|---|
| plugin-eval | 53/F | trigger+invoke 双超预算 |

## 关键发现

### 1. 同一个 skill，三个工具给出三种不同答案

以 root-cause-analysis 为例：
- plugin-eval 说 67/D（文件太长）
- skill-up 说 FAIL 0%（最终消息没写 null 这个词）
- agentut 说 100/100（DeepSeek 恰好用了 null 这个词）

三个都对，但评的是不同的东西：plugin-eval 评文件结构，skill-up 和 agentut 评最终消息的子串匹配（但用的模型不同，措辞不同，结果就不同）。

### 2. skill-up 的 judge 规则写错不报错

tdd-guide 失败的一半原因是我在 judge 里写了 output_contains AC1（这是 us-breakdown 的词）。skill-up 不会提示这个关键词跟 skill 无关。

### 3. 子串匹配跨模型不稳定

root-cause-analysis 在 skill-up（Claude）上 0%、在 agentut（DeepSeek）上 100%。因为 Claude 用了 undefined 而不是 null，DeepSeek 恰好用了 null。同一个断言关键词，模型不同结果就不同。

### 4. 无法运行的三个工具

skilljack-evals 最糟糕：静默失败，空结果算 FAIL，不提示缺 API key。skillgrade 六种 agent 全不兼容本机。comet 不是独立 CLI。

## 结论

三个能跑的开源工具没有一个能独立给出可信的行/不行判定。
plugin-eval 只看结构。skill-up 和 agentut 只看最终消息子串匹配。
能判断有没有用的对照组（lift）和能判断有没有走规定流程的工具调用链验证，目前只存在于自建工具中。
# 真实 Skill x 评测工具：最终对比数据

> 10 个真实 skill / 5 种工具 / 全部本机真跑

## 完整矩阵

| Skill | 环节 | plugin-eval | cc-eval路由 | cc-eval行为(lift) | agentut | skilljack |
|---|---|---|---|---|---|---|
| us-breakdown | 需求拆解(CLI) | 95/A | 3.8s PASS | **lift=1** | **100** 16s | 无法运行 |
| product-manager | 需求拆解(多agent) | **53/F** | 8.3s PASS | **lift=1** | — | — |
| tdd-guide | 写测试 | 77/C | 9.6s PASS | **lift=1** | **75**(文件名不匹配) | — |
| root-cause-analysis | 调试 | 67/D | 11.2s PASS | **lift=1** | **100** | — |
| requesting-code-review | 提交自查 | 81/C | 10.0s PASS | — | — | — |
| code-review(dsh) | 代码审查 | 72/C | 22.8s PASS | — | — | — |
| frontend-design | UI设计 | 67/D | PASS | **lift=1** | — | — |
| ping-check | 玩具 | 100/A | PASS | **lift=1**(3次) | **100** 7.2s | **静默失败** |

## 每个工具的实际评测方式

### plugin-eval
- 读文件 -> ceil(字符数/4) 估token -> 对比 Codex 基线常量 -> 结构检查
- 不跑模型、不执行脚本
- **分数与有用性不相关**（53/F 的能用，95/A 的 CLI 有 bug）
- 独有价值：**抓断链**（browser-to-api 的 broken-relative-links）

### cc-eval 路由（早停）
- 起 claude -> 每 400ms 读事件流 -> 见 Skill 调用就杀进程树
- 10/10 全触发，4-23s，$0
- **只验触发，不验后续**

### cc-eval 行为（两臂）
- 同一 prompt 跑两遍（装/不装 skill）-> 按轮断言 -> lift = with通过率 - without通过率
- 5 个跑了全量，全部 **lift=1**
- 独有断言：**must_call_tool**（验 CLI 被执行）、**两臂对照**

### agentut
- YAML 定义场景 -> 起 opencode(DeepSeek) -> 7种断言（should_call_tool 最强）
- 4 个 skill 测了：100/100/75/100
- **最快最便宜**：16s / $0.02
- 局限：should_produce_file 是精确匹配（不是 glob），tdd-guide 因此扣了 25 分

### skilljack-evals
- **需要 ANTHROPIC_API_KEY**，本机没有 -> 静默输出空结果 -> 空结果算 FAIL
- **不提示缺 key、不报错** —— 你会以为 skill 有问题，实际是评测工具没跑起来

### comet
- 不是独立评测 CLI，是 63MB 完整 agent 平台，不适合拿来对比

### skill-up
- 声明式 YAML + expect 短路 + judge 三层 + 多引擎适配器
- 之前已实测（ping PASS 13s、frontend-design PASS 195s）
- **judge YAML 写错不报错**（unknown_rule 静默算 FAIL）

## 结论

| 场景 | 推荐 | 原因 |
|---|---|---|
| 改完秒级自查 | plugin-eval | 免费、抓断链 |
| 确认触发 | cc-eval 路由 | 早停 4-11s |
| 发版决策 | cc-eval 行为 | 唯一有 lift |
| 高频回归 | agentut | 16s/$0.02 |
| 多引擎 | skill-up | 适配器全 |

**没有任何一个工具能独立给出可信的行/不行判定。**
可信的判定需要：结构检查 + 路由验证 + 两臂行为对照 + 多次重复 + 边界用例。
这个组合目前不存在于任何单一工具中。
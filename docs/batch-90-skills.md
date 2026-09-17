# 90 个真实 Skill 的批量静态分析（plugin-eval）

> 90 个 skill = 60 个来自 openai/plugins + 30 个本地（anthropics/DSH/skill-test-kit/SkillsMP/自建）
> 工具：plugin-eval（OpenAI 官方静态分析器，不跑模型，免费，每个 <1 秒）
> 全部在本机真实运行

## 总览

| 指标 | 值 |
|---|---|
| 总数 | 90 |
| 平均分 | 78.7 |
| 平均 trigger tokens | 82 |
| 平均 invoke tokens | 2245 |
| openai/plugins 平均 | 81.5 |
| 本地语料平均 | 73.0 |

## 等级分布

| 等级 | 数量 | 占比 | 说明 |
|---|---|---|---|
| A (90+) | 15 | 16.7% | 结构精简，预算合规 |
| B (85-89) | 20 | 22.2% | 基本合规 |
| C (70-84) | 34 | 37.8% | 有问题但不严重 |
| D (55-69) | 16 | 17.8% | 预算超标或结构问题 |
| F (<55) | 5 | 5.6% | 严重问题 |

## TOP 10（分数最高）

| Skill | 来源 | 分数 |
|---|---|---|
| swiftpm-macos | openai | 100/A |
| test-triage | openai | 100/A |
| packaging-notarization | openai | 100/A |
| signing-entitlements | openai | 100/A |
| us-breakdown | 本地 | 95/A |
| appkit-interop | openai | 95/A |
| grammar-of-graphics | openai | 95/A |
| statistical-visualization | openai | 95/A |
| ios-simulator-browser | openai | 95/A |
| ios-debugger-agent | openai | 95/A |

## BOTTOM 5（F 级）

| Skill | 来源 | 分数 | 主要问题 |
|---|---|---|---|
| product-manager | SkillsMP | 53 | trigger 186 + invoke 1663 双超预算 |
| dsh-trim-cot-leakage | DSH | 53 | 结构问题 |
| adobe-batch-edit-photos | openai | 54 | invoke 46214 极端超大 |
| adobe-retouch-portraits | openai | 54 | invoke 超大 |
| webapp-testing | anthropics | 54 | invoke + deferred 超预算 |

## invoke token 分布

| 范围 | 数量 |
|---|---|
| <500 | 8 |
| 500-2000 | 36 |
| 2000-5000 | 41 |
| >5000 | 5 |

## 关键发现

### 1. 大多数 skill 在 B-C 区间（60%），极端情况是少数

76.7% 的 skill 落在 B-C（70-89），说明大多数开发者写的 skill 结构基本合规，
但有 token 预算方面的改进空间。F 级只有 5 个（5.6%）。

### 2. openai/plugins 的 skill 比本地的平均分更高

openai/plugins 平均 81.5 分，本地语料（anthropics + DSH + 内部 + SkillsMP + 自建）平均 73.0 分。
可能因为 openai/plugins 有更多简短的技术指导 skill（如 swiftpm/signing 都在 100 分）。

### 3. Adobe 系列 skill 是 invoke token 的极端异常值

adobe-batch-edit-photos 的 invoke 是 46214 tokens（是平均值的 20 倍），
两个 Adobe skill 都是 F 级。这类 skill 把完整的操作手册塞进了 SKILL.md。

### 4. 评测基础设施 bug 可以产生大规模误导

本次实验中 PowerShell 下载 bug 导致文件内容变成字节值文本，
plugin-eval 对 57 个损坏文件全部给了 F——如果没发现这个 bug，
会得出 69% 的 openai skill 都是 F 级的错误结论。
修复后实际 F 级只有 5.6%。

## 注意事项

plugin-eval 只做静态分析（读文件、估 token、查结构），不跑模型。
分数高不代表 skill 能用，分数低不代表不能用（见之前的行为测试对比数据）。
它的独有价值是抓断链和极端预算异常，不是评判 skill 好坏。
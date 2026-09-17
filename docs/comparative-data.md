# 同一批真实 Skill × 四种评测工具的对比数据

> 日期：2026-09-16 · 这是调研数据，不是产品演示。
> 方法：挑 3 个有代表性的真实 skill，用 4 种工具各跑一遍，摆在同一张表里。
> 所有结果均为**本机真实运行**，不是文档转述。

---

## 1. 被测 Skill

| Skill | 形态 | 复杂度 |
|---|---|---|
| **us-breakdown** | 含 2 个真 CLI（parser + validator）+ 2 个 references + 多轮修订 | 最高 |
| **frontend-design** | 纯文本建议型（anthropics 官方），无产物文件 | 中 |
| **web-artifacts-builder** | 执行型（anthropics 官方），要跑 init/bundle 脚本 | 高（执行耗时） |

---

## 2. 对比矩阵（核心数据）

### us-breakdown（复杂：CLI + 验证环 + 多轮）

| 维度 | plugin-eval | cc-eval | skill-up | agentut |
|---|---|---|---|---|
| 引擎 | 不跑模型 | Claude Code | Claude Code | opencode + DeepSeek |
| 对照组 | 无 | **有（两臂）** | 无（可选，默认关） | 无 |
| **结论** | 95/A medium | **with PASS / without FAIL, lift=1** | FAIL 60%* | PASS 100 |
| 耗时 | <1s | 160s（2 轮） | 99s（1 轮） | **16s**（2 场景） |
| 成本 | 0 | $0.48 | ~$0.40 | ~$0.02（DeepSeek） |

*skill-up 的 60% FAIL 有一半是评测用例编写者的 YAML 语法错误（judge.success 里 file_contains 不是合法规则 → unknown_rule），去掉后实际 3/3 通过。

**各工具看到了什么（us-breakdown）**：

| 工具 | 看到了 | 没看到 |
|---|---|---|
| plugin-eval | deferred cost 偏重（references+scripts=950 tokens）；结构合规 | **一切行为**——不知道 skill 会不会被触发、CLI 会不会被跑、产物对不对 |
| cc-eval | skill 被加载；**CLI 真的被执行了**（must_call_tool）；产物内容对（AC 全覆盖）；多轮修订时验证环重跑了；**基线不装 skill 时什么都不产** → lift=1 | validator 的 exit code 是不是 0（只确认调了，没确认结果）；skill 处理"没有 AC 的 US"的边界行为 |
| skill-up | 文件存在（expect 过）；文件内容含 AC1 | **CLI 是否真的被执行**；与基线的差异（无对照组）；我的 YAML 写错了它的 judge 语法（unknown_rule 占了 2/5 的扣分） |
| agentut | skill 被加载（should_call_tool）；breakdown.json 产出且内容含 AC1 + test_hint；负例（不相关问题不触发）；**16 秒出结果** | CLI 是否真的被执行（只查文件，没查工具调用链）；与基线的差异 |

### frontend-design（纯文本建议型）

| 维度 | plugin-eval | cc-eval | skill-up | agentut |
|---|---|---|---|---|
| **结论** | **67/D high risk** | with 1/1 PASS, without 0/1, **lift=1** | PASS（首跑 240s 超时，600s 档通过） | 未测 |
| 耗时 | <1s | 107s | 195s + 1 次超时 | — |
| 关键发现 | invoke 2359 + deferred 2588 **超预算**；description 缺 "Use when" | 行为完全正常且增量明确 | 行为正常但**执行耗时超预期** | — |

**分歧**：plugin-eval 给了 D 级（预算超标），cc-eval 给了 PASS + lift=1（行为正常且有用）。**两者都没错**——一个管"写得贵不贵"，一个管"有没有用"。

### web-artifacts-builder（执行型）

| 维度 | plugin-eval | cc-eval | skill-up | agentut |
|---|---|---|---|---|
| **结论** | 77/C | 断言过但 **600s 超时**（未完成） | 未测 | 未测 |
| 关键发现 | 结构合规，预算在 C 档 | skill 被触发、index.html 产出，但任务没做完 | — | — |

---

## 3. 四种工具的能力边界（从数据推出）

| 能力 | plugin-eval | cc-eval | skill-up | agentut |
|---|---|---|---|---|
| 静态结构检查 | ✓ | oracle gate（部分） | validate 命令 | ✗ |
| token 预算审计 | ✓（三段拆解） | ✗ | ✗ | ✗ |
| 路由评测（触发率） | ✗ | ✓（早停 4s） | ✗ | ✓（should_call_tool） |
| 行为评测（产物） | ✗ | ✓ | ✓ | ✓ |
| 流程评测（CLI 被执行） | ✗ | ✓（must_call_tool） | ✗ | ✗ |
| 对照组（lift） | ✗ | **✓ 默认两臂** | 可选，默认关 | ✗ |
| 多轮对话 | ✗ | ✓（--resume + 按轮断言） | ✓（SessionResumer） | ✓（共享会话） |
| 统计口径 | 分数/等级 | **rate/Wilson/lift** | mean/delta | runs/min_pass |
| 速度 | **<1s** | 160s（全量）/ 4s（路由） | 99s | **16s** |
| 成本 | **0** | $0.48 | $0.40 | $0.02（DeepSeek） |

---

## 4. 四个工具都漏掉的（研究缺口）

以 us-breakdown 为例，**没有任何一个工具验证了以下事项**：

1. **CLI 的 exit code 是否为 0**——cc-eval 的 must_call_tool 确认了 validate_breakdown.mjs 被调用，但没有验证它的退出码（万一校验失败 agent 无视了呢？）
2. **验证环是否闭合**——skill 说"校验失败就修产物再跑"，但没有工具测试"agent 会不会在 validator 返回 1 时真的修复并重跑"
3. **边界 US 的行为**——没有工具测试"一条 AC 都没有的 US"进来时 skill 会怎样（parser 会 exit 1，agent 会不会优雅处理？）
4. **产物 schema 的深层校验**——breakdown.json 的 JSON 结构对不对、estimate_days 是不是都在 (0,1] 区间——这些 validator 脚本本身会查，但评测工具只做了子串匹配

---

## 5. 数据说话的结论

### 5.1 各工具的真实定位（从数据推出，不是从 README 推出）

- **plugin-eval**：一个**免费秒出的体检报告**。适合放在评测流水线的最前面当门卫（"写都写不好就别跑了"），但不能用它判断"skill 有没有用"。
- **cc-eval**：**唯一有对照组的**。能回答"装了这个 skill 比不装好多少"（lift），以及"agent 是否真的走了 skill 规定的流程"（must_call_tool）。但最贵、最慢。
- **skill-up**：**声明式 YAML + 引擎适配器**做得最好，一条配置就能跑 Claude Code/Codex/Qoder，产物生态位对齐 Anthropic。但 judge 语法有学习成本（我第一次就写错了），且默认不跑基线。
- **agentut**：**最快最便宜**（16s/$0.02），断言是工具级的（should_call_tool），适合高频回归。但只有 opencode 引擎、无对照组。

### 5.2 如果只选两个工具组合

- **日常开发回路**：plugin-eval（秒出）+ agentut（16s）→ 改完 skill 一分钟内知道"结构没问题 + 行为没退化"
- **发版决策**：cc-eval（两臂 lift）→ 确认"这个 skill 真的有增量价值，不只是模型本来就会"

### 5.3 需要进一步研究的问题（从缺口推出）

1. **CLI exit code 断言**：must_call_tool 应该支持 checking exit code / output content
2. **验证环闭环测试**：需要一个"故意让 validator 失败"的测试用例，验证 agent 会修复并重跑
3. **边界 US 测试**：用例应覆盖"无 AC""AC 互相矛盾""AC 不可测试"等异常输入
4. **产物 schema 深层校验**：用 JSON Schema 而非子串匹配来断言 breakdown.json 的结构
5. **跨模型一致性**：同一 skill 在 Claude/DeepSeek/GPT 上行为是否一致（我们已有 cc-eval 用 Claude、agentut 用 DeepSeek 的初步对比——都 PASS，但只有 1 次没有统计意义）

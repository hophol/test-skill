# 真实 Skill × 评测工具：最终对比数据（含开发循环 skill）

> 10 个真实 skill · 4 种工具 · 全部本机真跑 · 覆盖开发全循环（需求拆解→写代码→写测试→调试→代码审查→提交前自查）

---

## 完整对比矩阵

| Skill | 开发环节 | plugin-eval | 路由(早停) | 行为 with | 行为 without | lift |
|---|---|---|---|---|---|---|
| **us-breakdown** | 需求拆解(CLI) | 95/A | ✓ 3.8s | PASS 160s | FAIL 241s | **1** |
| **product-manager** | 需求拆解(多agent) | **53/F** | ✓ 8.3s | PASS 479s | FAIL 284s | **1** |
| **tdd-guide** | 写测试 | **77/C** | ✓ 9.6s | **PASS 191s/$0.79** | **FAIL 240s/$0.68** | **1** |
| **root-cause-analysis** | 调试 | **67/D** | ✓ 11.2s | **PASS 145s/$0.47** | **FAIL** | **1** |
| **requesting-code-review** | 提交前自查 | 81/C | ✓ 10.0s | — | — | — |
| **code-review**(dsh) | 代码审查 | 72/C | ✓ 22.8s | — | — | — |
| **team-qa** | 测试用例(多agent) | 77/C | ✓ 11.1s | — | — | — |
| **repo-health** | 代码健康扫描 | **67/D** | ✓ 7.5s | — | — | — |
| **browser-to-api** | API 提取 | **67/D** | ✓ 9.9s | — | — | — |
| **frontend-design** | UI 设计方向 | **67/D** | ✓ | PASS 108s | FAIL 44s | **1** |

**跑过全量行为评测的 5 个 skill，lift 全部 = 1**（装 skill 全 PASS、不装全 FAIL）。

---

## 每个工具对开发循环 skill 的实际表现

### plugin-eval（静态，免费，<1s）

| Skill | 分数 | 检查到的问题 |
|---|---|---|
| us-breakdown | 95/A | deferred 偏重 |
| product-manager | 53/F | trigger 186 + invoke 1663 超预算 |
| tdd-guide | 77/C | invoke 3393 超预算 |
| root-cause-analysis | 67/D | trigger 155 + invoke 1352 双超 |
| requesting-code-review | 81/C | — |
| code-review | 72/C | — |

**模式**：所有从 SkillsMP 找到的开发循环 skill 都在 C/D 区间——**不是它们不好，是 plugin-eval 的基线太紧**（Codex 的轻目录习惯 vs 这些 skill 动辄 1000-3000 tokens 的正文）。

**它抓到的真问题**：browser-to-api 有断链（所有行为测试都看不到）；us-breakdown 的 deferred 偏重提示可以精简 references。

### cc-eval 路由（早停，秒级）

10/10 全触发。**路由层几乎不会假阴性**——只要 description 里写了触发词，就能命中。开发循环的 skill 描述通常很清晰（"Write unit tests"、"Debug error"、"Review code"），所以路由全过。

### cc-eval 行为（两臂，分钟级）

5 个跑了全量，全部 **lift=1**。但过程有差异：

| Skill | with_skill 做了什么 | without_skill 做了什么 |
|---|---|---|
| tdd-guide | 加载 skill → 读源码 → 跑了 Bash(npm test) → 写了测试文件 → 测试通过 | 不调 skill → 也写了测试文件 → **但 must_call_skill 失败**（没走 TDD 流程） |
| root-cause-analysis | 加载 skill → 读源码 → 跑了多轮 Bash/Grep → **用 AskUserQuestion 向用户确认了修复方向** | 不调 skill → 也做了分析 → 但没走系统化 RCA 流程 |
| us-breakdown | 加载 skill → **跑了 2 个 CLI** → 产出 breakdown.json → validator 通过 | 什么都不产 |
| product-manager | 加载 skill → **即兴模拟了 5 人 agent 团队** → 产出 user stories | 自己去 SkillsMP 搜了一圈但没产出 |
| frontend-design | 加载 skill → 给出设计方向 | 不触发、答非所问 |

**关键洞察**：tdd-guide 和 root-cause-analysis 的 without_skill 臂**也能完成任务**（写测试、分析 bug）——**但没走 skill 规定的结构化流程**。lift=1 的来源是"流程合规"而非"能不能做"。如果只看最终产物质量（不看流程），这两个 skill 的 lift 可能远小于 1。

**这引出一个深层问题**：对于"提升工作质量而非解锁新能力"的 skill（如 TDD 流程、RCA 方法论），两臂对比的判据应该是什么？产物质量？流程遵循度？还是两者的组合？

---

## 更新后的结论

| 结论 | 证据 |
|---|---|
| plugin-eval 分数与有用性不相关 | 53/F 的 product-manager lift=1；95/A 的 us-breakdown CLI 有 bug |
| 所有开发循环 skill 都能正确触发 | 10/10 路由 PASS |
| 装了比不装好（lift=1）| 5/5 行为测试 PASS vs FAIL |
| **但"好在哪里"因 skill 类型而异** | us-breakdown：没它连产物都不产；tdd-guide：没它也能写测试但没走 TDD 流程 |
| 静态检查有独特价值 | browser-to-api 的断链只有 plugin-eval 抓到 |
| **流程型 skill 的评测需要新判据** | 两臂产物可能都"能看"，差异在过程（工具调用序列、是否问了用户、是否跑了测试） |

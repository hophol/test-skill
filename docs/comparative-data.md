# 真实 Skill × 评测工具：完整对比数据

> 日期：2026-09-16 · 全部为本机真实运行结果，非文档转述。
> 6 个真实 skill（3 个来自 SkillsMP marketplace，3 个来自 anthropics/内部），用 4 种工具各跑，看每个工具**实际检查了什么、怎么检查的、结果是什么**。

---

## 1. 被测 Skill 全景

| Skill | 来源 | 形态 | plugin-eval | 路由触发 | 行为结果 |
|---|---|---|---|---|---|
| **us-breakdown** | 自建 | 含 2 个 CLI + 验证环 | 95/A | ✓ 3.8s | with PASS / without FAIL, **lift=1** |
| **product-manager** | SkillsMP | 多 agent PM 全流程 | **53/F** | ✓ 8.3s | with PASS / without FAIL, **lift=1** |
| **frontend-design** | anthropics | 纯文本建议型 | **67/D** | ✓（已有） | with PASS / without FAIL, **lift=1** |
| **team-qa** | SkillsMP | 多 agent QA 测试用例 | **77/C** | ✓ 11.1s | 未跑全量 |
| **repo-health** | SkillsMP | 脚本扫描型（TODO/FIXME） | **67/D** | ✓ 7.5s | 未跑全量 |
| **browser-to-api** | SkillsMP | 外部依赖型（浏览器 trace） | **67/D** | ✓ 9.9s | 未跑全量 |

---

## 2. 每个工具的评测机制（从源码 + 实测还原）

### 2.1 plugin-eval：它到底检查了什么

**机制**：不跑模型。读 SKILL.md 文件 → 用 `ceil(字符数/4)` 估 token → 对比 Codex 基线常量 → 检查结构。

**对 6 个 skill 的实际输出**：

| Skill | score | 检查到的问题 | 它没看到的 |
|---|---|---|---|
| us-breakdown | 95/A | deferred 偏重(950) | **CLI 脚本里的 2 个 bug**（漏 AC、没剥 BOM） |
| product-manager | 53/F | 描述 186 tokens 太长、正文 1663 超预算 | **skill 实际能工作，lift=1** |
| frontend-design | 67/D | invoke 2359 + deferred 2588 超预算 | **skill 实际能工作，lift=1** |
| team-qa | 77/C | invoke 2992 超预算、description 触发语弱 | 未验证是否真的能写出测试用例 |
| repo-health | 67/D | trigger 168 **和** invoke 3154 都超预算 | 未验证扫描脚本是否能跑 |
| browser-to-api | 67/D | **有断链**（broken-relative-links）| 未验证是否能解析浏览器 trace |

**结论**：分数与"有没有用"**不相关**。53/F 的能用，95/A 的有 bug。唯一有价值的是 browser-to-api 的断链检查——这是一个所有行为测试都看不到的真问题。

### 2.2 cc-eval 路由（T1 早停）：它到底检查了什么

**机制**：起一个 claude -p 进程 → 每 400ms 读事件流文件 → 看到 `"name":"Skill"` 就杀进程树 → 检查是否调用了期望的 skill。

**对 6 个 skill 的结果**：

| Skill | 触发？ | 耗时 | 说明 |
|---|---|---|---|
| us-breakdown | ✓ | 3.8s | "拆解用户故事" → 命中 |
| product-manager | ✓ | 8.3s | "Decompose user stories" → 命中 |
| frontend-design | ✓ | ~10s | "设计方向" → 命中 |
| team-qa | ✓ | 11.1s | "Write test cases" → 命中 |
| repo-health | ✓ | 7.5s | "Scan for TODO" → 命中 |
| browser-to-api | ✓ | 9.9s | "Extract API from browser" → 命中 |

**结论**：路由层很可靠——只要 description 里写了触发词，就能命中。但这只说明"会触发"，不说明"触发了之后干的事对不对"。

### 2.3 cc-eval 行为（T3 两臂）：它到底检查了什么

**机制**：同一 prompt 跑两遍（装 skill / 不装 skill）→ 按轮断言（工具调用、产物文件、内容子串）→ lift = with通过率 − without通过率。

**对 3 个 skill 跑了全量**：

| Skill | with_skill | without_skill | lift | with 做了什么 | without 做了什么 |
|---|---|---|---|---|---|
| us-breakdown | PASS(160s/$0.48) | FAIL(241s/$0.59) | **1** | 跑了 CLI、产了 breakdown.json、validator 通过 | 什么都没产 |
| product-manager | PASS(479s/$1.31) | FAIL(284s/$0.90) | **1** | 即兴模拟多 agent、产出 user stories + AC | 自己去 SkillsMP 搜了一圈但没产出 |
| frontend-design | PASS(108s/$0.20) | FAIL(44s/$0.10) | **1** | 给出配色/字体方向 | 不触发 skill、答非所问 |

**cc-eval 独有的断言**（其它工具没有）：
- `must_call_tool`：验证 CLI 是否真的被执行（us-breakdown 的 parser 和 validator）
- `must_not_reask`：验证是否重复追问已确认的信息
- **两臂对照**：唯一能回答"比不用好多少"的指标

### 2.4 skill-up：它到底检查了什么

**机制**：声明式 YAML（expect + judge）→ 起 claude 进程 → expect 零成本预检（失败短路跳过 judge）→ judge 判分。

**对 us-breakdown 的实际运行**：

~~~
我写的 YAML：
  judge.success:
    - file_contains:
        - path: "breakdown.json"
          content: "AC1"

skill-up 实际执行：
  → expect.files_exist: breakdown.json → PASS
  → expect.file_contains: AC1 → PASS
  → judge.success[0]: files_exist → PASS
  → judge.success[1]: file_contains → **unknown_rule**（FAIL）
  → judge.success[2]: file_contains → **unknown_rule**（FAIL）
  → 总分 3/5 = 60% FAIL

问题：file_contains 在 judge.success 里不是合法规则类型，
skill-up 不报错、不警告，直接算 FAIL。
~~~

**结论**：声明式 YAML 的学习成本比预期高——**写错了它不会告诉你**。unknown_rule 静默地变成扣分项。

### 2.5 agentut：它到底检查了什么

**机制**：YAML 定义场景和断言 → 起 opencode 进程（DeepSeek）→ 断言分 7 种（should_call_tool 最强）→ 断言分 = round(通过数/总数×100)。

**对 us-breakdown 的实际运行**：

~~~
断言：
  1. should_call_tool: {name: Skill, input: {name: us-breakdown}, status: completed}
     → 检查事件流里是否有 name=Skill 的 tool_use 且参数包含 "us-breakdown" → ✓
  2. should_produce_file: breakdown.json
     → 递归扫工作目录 → ✓
  3. file_content_contains: {file: breakdown.json, text: "AC1"}
     → 读文件查子串 → ✓
  4. file_content_contains: {file: breakdown.json, text: "test_hint"}
     → 读文件查子串 → ✓

结果：4/4 = 100 分，16 秒
~~~

**它没检查的**：
- CLI（us_parser.mjs / validate_breakdown.mjs）是否真的被 Bash 执行了
- breakdown.json 的 JSON 结构是否合法
- estimate_days 是否在 (0,1] 区间
- 与没有 skill 时的基线差异

**结论**：最快（16s）最便宜（$0.02），但断言停留在"文件存在 + 子串匹配"级别。

---

## 3. 核心对比表

| 维度 | plugin-eval | cc-eval 路由 | cc-eval 行为 | skill-up | agentut |
|---|---|---|---|---|---|
| **跑模型？** | ✗ | ✓（早停杀树） | ✓（全程） | ✓ | ✓ |
| **检查什么** | 文本结构+token 估算 | 是否调用 Skill 工具 | 工具调用链+产物+内容 | expect 预检 + judge 规则 | 工具调用+产物+子串 |
| **有对照组？** | ✗ | ✗ | **✓** | ✗ | ✗ |
| **验 CLI 执行？** | ✗ | ✗ | **✓** | ✗ | ✗ |
| **验内容质量？** | 结构规则 | ✗ | 子串匹配 | 子串/正则 | 子串匹配 |
| **用时** | <1s | 4-11s | 160-479s | 99s | **16s** |
| **成本** | **$0** | ~$0 | $0.20-$1.31 | ~$0.40 | **$0.02** |
| **写错会怎样** | N/A（无配置） | N/A（早停固定） | oracle gate 拦截 | **静默 FAIL（unknown_rule）** | 断言不匹配就扣分 |

---

## 4. 分歧案例：最能说明问题的地方

### product-manager：plugin-eval 给 53/F，行为测试给 PASS + lift=1

**plugin-eval 看到的**：描述 186 tokens（太长）、正文 1663 tokens（超 Codex 基线）→ 严重扣分 → F

**cc-eval 看到的**：skill 被触发 → agent 读 PRD → 即兴模拟多 agent 协作 → 产出标准格式 user stories + AC → without_skill 时基线连格式都不对 → **lift=1**

**两者都没错，但回答的是不同问题**。plugin-eval 管"写得规范吗"，cc-eval 管"有没有用"。**只有后者能支持上线决策。**

### browser-to-api：plugin-eval 抓到了断链，行为测试没测到

**plugin-eval 看到的**：broken-relative-links（引用了不存在的外部文件）

**cc-eval 路由看到的**：触发了（9.9s）

**如果跑全量行为测试**：大概率也会 PASS（skill 被加载、agent 会尝试工作）——但断链意味着某些 reference 文件缺失，agent 可能会跳过或即兴发挥，产出质量可能打折。**这是行为测试的盲区：只要 skill 的 description 够好、正文的主要流程够清晰，即使引用断了也可能"看起来能用"。**

---

## 5. 结论：每个工具的真实价值

| 工具 | 真实价值 | 什么时候用 |
|---|---|---|
| plugin-eval | **结构门卫**：抓断链、查 token 预算、验 frontmatter | 改完 skill 后秒级自查 |
| cc-eval 路由 | **触发验证**：确认 description 写得够不够好 | 改 description 后 |
| cc-eval 行为 | **唯一能回答"有没有用"的**（lift） | 发版决策 |
| skill-up | 引擎适配器好，但 judge YAML 写错不报错 | 需要多引擎（Codex/Qoder）时 |
| agentut | 最快最便宜的回归冒烟 | 每次改 skill 后的"没崩吧"检查 |

**没有一个工具能独立给出可信的"行/不行"。可信的判定需要：结构检查 + 路由验证 + 两臂行为对照 + 多次重复 + 边界用例。这个组合目前不存在于任何单一工具中。**

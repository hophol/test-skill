# 收敛方案：B 组合（M4+M5+M2+M7小面积+M9）· 个人机全流程

> 定位：不预设公司落地，在个人机上把 B 组合**完整做通、做出数据**，产出工具包与实测结论。
> 发散依据见《发散-结果正确性如何自动判定.md》；v1 底座 = `D:\work\skill-test-kit\`（L1 已闭环）。

---

## 1. 目标与「做通」的验收标准

在现有 3 连样本 skill（fe-req-analysis → fe-dev-design → fe-test-design）上：

1. **C2/C3 分开断言、分开报告**的全链路套件跑通（含一次三连链式任务：原始需求进，
   追溯矩阵出）；
2. **judgeless 比例有数字**：C2+C3 断言总量中确定性断言占比（目标 ≥80%，M7 只盖残差）；
3. **M9 变异实验有灵敏度数据**：≥10 个变异体，报告抓住/漏过清单（目标抓住 ≥8）；
4. v1→v2 对照实测（同一批任务，v1 只能判触发，v2 能判什么）沉淀成经验文档。

## 2. 核心新资产：`tests/contract.yaml`（skill 随附机读契约）

v2 与 v1 的分野就在这里——**被测资产要规约化**。每个 skill 交一份契约，四段各自喂给一个检查器：

```yaml
# <skill>/tests/contract.yaml —— 以 fe-test-design 为例
process:                      # → M4 步骤合同（全部断言在事件层，不碰文本）
  must_use:                   # 无序集合：至少各调用一次，可带参数约束
    - { tool: Read,  args: { file: "req|需求|方案" } }   # 步骤1：读的必须是上游文档
    - { tool: Write, args: { file: "^fe-test-.*\\.md$" } } # 步骤5：产物文件名契约
  ordered: [ [Read, Write] ]  # 相对顺序：先读后写
  forbidden: [Edit, Bash]     # 边界：不改上游、不跑代码（对应 SKILL.md「边界」节）
output:                       # → M1/M5 产物契约
  artifact: "fe-test-*.md"
  required_sections: [单元, 组件, E2E, 验收核对表]
trace:                        # → M5 链路追溯规则
  consumes: ["fe-req-*.md"]   # 消费哪些上游产物
  id_pattern: "REQ-\\d+"
  rules:
    - every_upstream_id_covered_ge_1    # 每个 REQ ≥1 条用例
    - no_phantom_ids                    # 引用的 ID 必须真实存在于上游
invariants:                   # → M2 局部属性
  - { id: case-has-req,  check: every_case_references_id }
  - { id: sections-fixed, check: required_sections }
metamorphic:                  # → M2 蜕变（跨运行，人工论证后才准上线）
  - id: add-req-grows-cases
    transform: 上游需求 +1 条 REQ
    expect: 用例集覆盖新 REQ 且总数不减
```

**关键决策：契约先手写，不做 SKILL.md 自动抽取**（抽取器是后续项）。
防双份漂移兜底：contract-lint 加一道「process 步骤 ↔ SKILL.md 流程章节」条目数/关键词
一致性检查，对不上就报错——合同说 5 步、SKILL.md 写 4 步，必须有人裁决哪个是对的。

## 3. 组件设计（5 个小组件，全部挂在 v1 执行底座上）

| 组件 | 干什么 | 判定 | 实现 |
|---|---|---|---|
| contract-lint | 契约可解析、与 SKILL.md 不矛盾 | 确定性 | Python，~100 行 |
| trace-assert (M4) | 从会话转录断言 process 合同（工具/参数/顺序/禁令） | 确定性 | 复用 v1 转录解析，新增参数级匹配 |
| chain-check (M5) | 上游+下游产物 + trace 规则 → 覆盖率、幻觉 ID、双向追溯矩阵 | 确定性 | Python，核心是 ID 集合运算 |
| prop-check (M2) | 局部属性 + 幂等（跑两遍结构等价）+ 蜕变（输入变换→输出可预测变化） | 确定性 | Python；蜕变=受控改上游 fixture 再跑一轮 |
| mutant-runner (M9) | 对 skill 注入变异体 → 跑子套件 → 灵敏度报告 | 确定性 | 变异体=预定义补丁，见 §5 |

M7 残差裁判（对抗证伪式提示词：「找出该产物不满足任务要求的证据」，逐项二值+引用证据）
只挂在**锚点任务**上——链路/属性全过、但开放性维度（如「用例设计是否真的可执行」）
仍需判断的少数任务。裁判断言数占比目标 <20%。

## 4. 任务集（在 v1 探针之外新增 golden 任务层）

- 每 skill 3-5 个 golden 任务：输入 fixture（带完整 REQ-ID 的需求文档等）+ 指向契约的断言；
- **三连链式任务**（v2 的招牌演示）：原始需求 → req-analysis → 产物落盘 → dev-design 消费 →
  test-design 消费 → chain-check 出全链路追溯矩阵。用小编排脚本串三个无头会话，复用 v1 runner；
- 任务工作区沿用 v1 分区纪律（素材只在正向区）。

## 5. 变异体清单（M9，先 10 个）

| # | 变异 | 应被哪个组件抓住 |
|---|---|---|
| 1 | 删流程步骤4（E2E 场景） | prop-check sections / output |
| 2 | 「缺则先指出，不猜」→「合理推断补全」 | trace-assert（Read 参数约束）|
| 3 | REQ 关联改为可选 | invariants case-has-req |
| 4 | 产物文件名改为自由命名 | trace-assert Write 参数 |
| 5 | 章节改名 | prop-check sections-fixed |
| 6 | 删「不改需求/方案」边界 | forbidden 断言 |
| 7 | 步骤顺序倒置（先写后读） | ordered 断言 |
| 8 | description 改得无法触发 | v1 L1 探针（顺便验证两层互补）|
| 9 | 引用不存在的模板文件 | L0/contract-lint |
| 10 | 输入 +1 需求但用例不增 | 蜕变 add-req-grows-cases |

漏抓定性规则：变异被「语义等价」挽救（如删了步骤模型自己补上）记为套件盲区，不是误报。

## 6. 实施阶段（每段有验收，预计 4 个工作日）

| 阶段 | 内容 | 验收 |
|---|---|---|
| P1（0.5d） | 契约格式定稿 + contract-lint + 3 个样本 skill 补 contract.yaml | lint 全绿；故意制造一处合同/SKILL.md 不一致能被抓 |
| P2（1d） | trace-assert + prop-check，单 skill（fe-test-design）跑通 C2/C3 | 一个真任务出 C2/C3 分栏报告；C2 断言全在事件层 |
| P3（1d） | chain-check + 三连链式任务端到端 | 原始需求进，追溯矩阵出；故意删一条 REQ 覆盖能报红 |
| P4（1d） | M7 裁判挂载 + M9 变异实验 | 灵敏度报告（≥8/10）；裁判断言占比 <20% |
| P5（0.5d） | 数据沉淀：v1/v2 对照、灵敏度、token/耗时 | 经验文档一篇，进 skilltest-v2/ |

## 7. 目录与复用

```
skilltest-v2/
├── 发散-*.md / 收敛方案-*.md        # 本组文档
├── kit/                             # v2 工具包（新起，不污染 v1 基线）
│   ├── skills-sample/               # 从 skill-test-kit 拷入 6 个样本，3 个主测 skill 补 tests/
│   ├── scripts/                     # 5 个新组件 + 拷入 v1 的 runner/转录解析复用
│   ├── tasks/                       # golden 任务 + 三连链式编排
│   └── mutants/                     # 变异体补丁
└── results/                         # 实测数据（含 v1/v2 对照）
```

v1 的 `skill-test-kit` 保持原样作为对照基线；`PITFALLS.md` 的 11 条直接继承（编码、
max_turns、探针自包含、bustCache 等全部适用）。

## 8. 风险与边界（实事求是）

- **手写契约漂移**：lint 一致性检查兜底，但本质上是双份维护——数据要记录这个成本；
- **蜕变不变量假绿**：每条 metamorphic 上线前在文档里人工论证一次（为什么该不变量必然成立）；
- **M9 漏抓 ≠ 套件差**：先定性（语义等价挽救 or 真盲区）再下结论；
- **裁判面积失控**：M7 只许挂在锚点任务，跑一次统计一次占比，超 20% 说明契约没写够，回 P1 补契约；
- token 预算粗估：P2-P4 全部实验 ≈ 60-100 个会话（含幂等翻倍、蜕变加跑、10 变异体），
  按之前实测（26 探针 89.5 万 token）推算在 300-500 万 token 量级；
- **明确不做**：公司落地推线、M3/M8/M10（激进组合项，列为后续）、契约自动抽取。

---

## 9. P1 定稿记录（2026-09-01 实施）

契约格式相对 §2 草案的四处增补（实施时定稿）：
1. `process.steps`（新增）：漂移哨兵，必须等于 SKILL.md「流程」编号条数——lint 抓"契约说 5 步、SKILL.md 写 4 步"；
2. `process.should_use`（新增）：软断言语义（缺失 = WARN 而非 FAIL），给条件步骤用（如"工作区有 package.json 才要求先读"）；
3. `args` 参数名改用转录真实参数名 `file_path`（草案写的 `file` 在 stream-json 里不存在）；
4. invariant 支持可选 `id_pattern` 参数（编号类检查的 ID 规范就近声明），`every_item_numbered` 支持可选 `sections` 限定检查范围。

**P1 期间发现的真实链路断点（已修）**：fe-test-design 承诺"每条用例关联 REQ-xxx"，但 fe-req-analysis 从未承诺发放编号——下游引用的编号规范上游不存在。修法：给 fe-req-analysis 步骤 5 补"REQ-001 起连续编号，编号由本 skill 统一发放"。这正是 M5 契约视角的价值：**不用跑任何会话，光写契约就把链路缺口暴露了**。
另留一个已知缺口不修：fe-dev-design 产物不挂 REQ 编号，P3 拿实测覆盖率数据（预期 0%）再决定。

产出：`kit/scripts/contract_lint.py`（结构 + 5 类漂移哨兵）、`kit/scripts/lint_selftest.py`（4 注入缺陷全抓）、3 份 `tests/contract.yaml`。验收：lint 全绿 + 自检 7/7 通过。

---

## 10. P2 实施记录（2026-09-01，fe-test-design 真任务 × 2 轮）

**交付**：`trace_assert.py`（M4）、`prop_check.py`（M2，含幂等比对）、`run_task.py`（端到端编排）、
`offline_selftest.py`（12 用例离线自检全过）。两轮真会话（200s / 111s，glm-5.3）。

**两轮实测结果**：C2 全 PASS（Read 参数匹配/Write 路径匹配/顺序/禁令）；C3 均 FAIL——
**确定性层抓到第一个真实缺陷**（非植入）：run-1 有 7 个、run-2 有 5 个用例单元未挂 REQ，
两轮独立出现、模式一致（全是页签切换/默认渲染类测试点）。

**根因定性（链路编号范围缺口，系统性）**：fe-req-analysis 步骤 5 只给「交互说明/边界条件」编号，
「页面清单/组件区块」级的行为性需求（默认态、渲染态、页签行为）没有编号 → 下游测试设计
想挂也挂不上，只能裸条目。这是**契约设计的缺口**，不是模型执行走样——v2 套件不跑会话光靠
写契约发现不了它（P1 只暴露了「REQ 规范谁发放」，P2 暴露了「编号范围过窄」）。

**判定器自身被真产物修理了三次**（离线自检全部覆盖回归）：
1. Write 参数正则原来锚定行首——转录里 file_path 是绝对路径，改为锚尾；
2. 单元提取原来只认列表项——真产物用例是「### 组标题｜REQ + 表格」形态，0 列表项 = 空转 PASS（假绿）；
   改为块归属语义：组标题挂编号 → 整块覆盖；未挂 → 块内条目/表格行逐一查，表头豁免；
3. 幂等签名原来按标题原文做键——章节措辞差异产生幻影漂移，改为规范章节名归并 + 非规约章节聚合。
   **教训：断言器对产物形态的假设，必须拿第一份真实产物校准——离线自检过了不代表判定语义对。**

**幂等实测**：WARN（真实信号）——`组件`章节两轮组织方式不同（24 单元+1 覆盖块 vs 3 单元+4 覆盖块），
用例粒度跨运行不稳定；E2E 两轮均 9 条（稳定）。skill 未钉死用例粒度/组织形态，这是
「输出契约只约束章节、不约束单元形态」的直接后果，留待 P3 后决定是否在 SKILL.md 钉格式。

**待裁决（进 P3 前定）**：孤儿用例的处置策略，见任务清单。
用户裁决（2026-09-01）：**维持严格，孤儿 FAIL 即治理信号**（待溯源清单交人工裁决），skill 与契约都不改。

---

## 11. P3 半程记录（2026-09-01，链路首跑 + 限额中断）

**已验证的部分**：
- 阶段 1（fe-req-analysis，96s）全链正常：C2 PASS；C3 FAIL 报 12 个未编号单元——治理信号在
  **源头**复现（页面清单/组件区块级条目），与 P2 下游孤儿同根因，闭环互证；
- 负向验收 ✓：把 REQ-004 改成不存在编号，chain-check 立即报红（漏覆盖+幻觉双报）；
- req→dev 链路幻觉检查 PASS（0 幻觉；信息性覆盖率 21/22）；
- UNKNOWN 纪律两次正确触发（阶段 2/3），没有把事故误判为过程失败。

**中断与诊断（限额 + 判定精度两处加固）**：
- 阶段 2：会话超 300s 被 subprocess 杀死，产物已写出但转录 0 字节 → 证据丢失形态（v1 经验三翻版）；
- 阶段 3：429 限额（5 小时上限），会话未启动，无产物；
- 加固 1：trace_assert 事故三分类——空转录 / API 错误文本 = 基础设施 UNKNOWN（不算 C1），
  有事件无 Skill 调用才是 C1 miss，有事件无 result 是截断；离线自检补两用例（14/14）；
- 加固 2：会话超时 300s→600s（阶段 2 实测需要 >300s）。
- 限额 17:01 重置后重跑完整链（run_chain 已就绪）。

**P4 基础设施已备好（等限额）**：mutants/mutants.json（10 变异体，标预期抓捕层与成本）、
run_mutants.py（基线差分：治理性 FAIL 不算抓变异，只有新增 FAIL 才算）、
judge.py + tasks/rubric-001.json（对抗证伪式裁判，4 检查项，裸会话只读）。

### P3 完成记录（17:04 限额重置后重跑，chain-20260901-170419）

**三阶段全通**：fe-req-analysis（130.7s，C2 PASS / C3 治理 FAIL×10——源头信号稳定复现）、
fe-dev-design（161.5s，**C2 PASS**——上一轮「未触发」确系超时证据丢失假象，三分类修复生效）、
fe-test-design（210.3s，C2 PASS / C3 治理 FAIL×30）。

**链路实测（req→test）**：覆盖率 **84.6%**（22/26），0 幻觉；req→dev 92.3%（24/26），0 幻觉。
4 个漏覆盖 REQ 人工定性为两类：
- REQ-004/005/006「**测了没挂号**」：都是「校验同 REQ-003」的衍生条目，测试设计实质覆盖了
  （验证码/校验相关内容 25 行）但没单独挂这三个 id——id 级追溯与实质覆盖的偏差；
- REQ-026「**上游噪声**」：req skill 给「本期不涉及权限场景」这条**非需求陈述**也发了号，
  下游合理地不测它，覆盖率矩阵反而冤枉下游。
  → 治理启示：覆盖率矩阵需要「等同覆盖（同 REQ-003 类）」与「N/A 豁免」两种人工标注位，
  以及生产者侧「非需求陈述不编号」的纪律（改 SKILL.md 的事，留作后续，先记录）。

**负向验收（用已覆盖的 REQ-001 重做，4 处引用→REQ-0119）**：同时触发 漏覆盖+幻觉编号，
覆盖率 84.6%→80.8%，矩阵 26 行完整输出。首跑用 REQ-004 做的负向是退化的（本来就漏覆盖）——
**负向演示必须选已覆盖的 id，否则证明不了任何东西**。

---

## 12. P4 实施记录（2026-09-01，变异 + 裁判）

**变异实验**：灵敏度 **5/10**（低于 8/10 目标，漏抓定性后结论反而更有价值）：
- 抓住：M1/M9/M10（L0 静态哨兵，零会话）+ M4/M5（动态）；
- 漏抓 5 个的分类：4 个是**任务集覆盖面**问题（素材缺失场景/诱惑场景/干扰池缺失），
  1 个是语义等价挽救（M7 模型自救）——「golden 任务的覆盖面决定灵敏度」，v1「探针质量
  决定一切」的 v2 对应物；
- 意外收获 1：**基线自己抓了个偶发真违规**——会话试图 Edit 自己的产物（修订待确认项），
  forbidden 无差别抓获 → 契约过宽的改进项（禁改上游应带参数约束）；
- 意外收获 2：M4 骗过了 L0 前缀哨兵（skill 名 fe-test-design 恰好含产物前缀 fe-test-），
  靠动态层兜住 → 哨兵应排除 frontmatter name；
- 方法论：基线差分（治理性已知 FAIL 不算抓住，只有新增 FAIL 算）——严格模式下必需，
  否则治理信号会虚增灵敏度。

**裁判（M7）**：两轮均被输出截断（无 result 事件，工程问题：输出预算/轮次），
但第二轮在 rubric 清单未送达的情况下**自行从技能契约推导 9 项检查清单**逐项证伪，
fail 项（用例未挂 REQ）与确定性层同证据收敛（L73/L84-86 同一批孤儿）——
**对抗裁判与确定性断言的收敛，是确定性层够用的最强佐证**。裁判面积：任务级 24%、套件级 <10%。

---

## 13. P5 收尾（2026-09-01）

全部数据、v1/v2 对照、成本、backlog 见《实测数据汇总-20260901.md》。
一句话总结：**v2 在一个工作日内，用 19 个会话 / 约 43 万 token，把 v1 测不了的
「过程对不对、结果对不对、链路通不通」变成可确定性判定的断言，抓获 10 项真实缺陷
（2 项零会话），并用变异实验和独立裁判交叉验证了套件自身的可信度。**

**P1-P5 验收对照**：P1 ✓（lint 全绿+注入全抓）；P2 ✓（C2/C3 分栏报告+真缺陷）；
P3 ✓（三连链路+追溯矩阵+负向报红）；P4 部分（灵敏度 5/10 < 8/10 目标，漏抓已全数定性，
改进路径明确；裁判截断未完整执行）；P5 ✓（本文档族）。

---

## 14. 外部 skill 入池记录（2026-09-01 晚，P6 计划外增量）

**来源与选择**：anthropics/skills@main（与池内原有 3 个外部 skill 同源，供应链风险最低）。
候选 4 个前端相关 skill，入池 3 个：**brand-guidelines / theme-factory / algorithmic-art**；
**跳过 canvas-design**（80 个 ttf 字体 ~5MB 二进制，审计成本/收益不划算）。

**安全审核（v1 PITFALLS #11 流程，3/3 通过）**：
- 逐文件通读：3 份 SKILL.md + generator_template.js + viewer.html 全文审过；
- 危险模式全量 grep（网络/执行/安装/混淆/持久化）：唯一外联 = cdnjs 的 p5.js 1.7.0（版本锁定）
  + Google Fonts，均为良性；无 eval/fetch/subprocess/安装指令；
- PDF（theme-showcase.pdf, 124KB）：/JavaScript /JS /OpenAction /Launch /EmbeddedFile 全零；
  12 处 `/AA` 逐一定性为 `/AAAAAA+字体子集名` 前缀（DejaVu/FreeSans 等），排除。

**契约格式第三次扩展（外部 skill 逼出来的 4 项）**：
1. `process.steps` 可选（外部 skill 无「流程」章节，哨兵降为提示）；
2. `output.required_sections` 可选（无章节承诺时不硬造断言）；
3. `output.artifacts`（glob 列表）—— 多产物契约（algorithmic-art 承诺 .md+.html+.js 三件套）；
4. `output.contains`（正则列表，并集语义）—— v1 的 file_contains 升格进契约，品牌色/主题色板
   的确定性断言靠它；配套 `output.naming: task|skill`（外部 skill 产物命名由任务指定，
   跳过 SKILL.md 前缀哨兵）。
   顺手修了 prop_check 一个 P2 潜伏 bug（invariant 循环变量泄漏，多 invariant 带_sections 时取错）。

**任务设计的关键一课**：theme-factory 的原生流程是交互式（展示 showcase → 问用户 → 等确认），
无头模式必卡死——**任务预选主题并在 prompt 里明说「无需展示/询问」**，绕过后 64s 跑通，
且 must_use `Read themes[/\]` 命中证明它真的读了主题定义才动手。

**实测结果（3 任务，glm-5.3）**：

| 任务 | 耗时 | token | 结果 |
|---|---|---|---|
| 002 brand-styling | 107s | 34k | PASS：品牌色 hex×3 + 双字体族 5 项 contains 全命中 |
| 003 theme-arctic | 64s | 32k | PASS：Arctic Frost 4 色 + 字体全命中 |
| 004 algo-art | 522s | 94k | C3 PASS（三件套齐+p5+种子随机）、**C2 FAIL：Bash×3** |

004 的 FAIL 定性：三次 Bash 全是 `node --check generator.js`——agent 对自己产物做**语法自检**，
良性甚至值得鼓励。与变异基线「Edit 自己草稿」同模式，**当日第三次出现**：
全称 forbidden 抓「调用意图」不抓「危害」，自校验类行为是系统性假阳性来源
（改进：forbidden 参数化 / Bash 子命令白名单，已列 backlog 首位）。

---

## 15. 第二批外部入池（2026-09-01 晚，社区多作者扩池）

**来源**：VoltAgent/awesome-agent-skills 目录（链接目录，不托管）定位到各团队仓库，jsDelivr 拉取。
5 候选入池 4，**池子 9 → 13**（6 自建 + 3 anthropics + 4 社区/官方多作者）。

| skill | 作者 | 审计结论 | golden 任务 |
|---|---|---|---|
| angular-developer | Angular/Google 官方 | 38 个 reference 纯文档，通过 | 005 PASS（44s；ng build 软断言按预期 WARN 不 FAIL）|
| fixing-accessibility | ibelick | 单文件规则表，通过 | 006 PASS（104s；4 个修复特征全命中）|
| ui-ux-pro-max | nextlevelbuilder | 脚本全 stdlib+原子写+防路径穿越，但 **`design_system.py` 顶层 import `reasoning_contract` 模块仓库里不存在——发布缺陷，静态审计抓获** | 007 C3 PASS / C2 FAIL（见下）|
| react-email | Resend 官方 | 文档型，通过 | 008 PASS（249s；600px 版心只在 html 命中，并集语义正确）|
| web-perf | Cloudflare 官方 | 干净，但 **MCP 依赖型**（SKILL 明令无 chrome-devtools MCP 即 STOP）——无头环境不可测，**跳过，新类别记录在案** | — |

**新类别发现（扩池的直接收益）**：
1. **MCP 依赖型 skill**：测试前提是外部 MCP server，无头套件天然覆盖不了——上量之前必须先分类；
2. **脚本依赖型 skill**（ui-ux-pro-max）：设计上就要执行自带脚本，无头禁 Bash 则 C2 必 FAIL
   （实测 8 次尝试）；脚本还坏了（缺模块），靠 data/ 数据文件降级可用——C3 仍可判定；
3. **会话经济学**：007 首跑 12 轮耗尽（20 个 CSV 数据文件太能吃轮次），22 轮才产出——
   数据重型 skill 的 max-turns 要按数据规模给。

**判定器同步加固**：CLI 在 max-turns 截断时也会发 result 事件（subtype=error_max_turns、文本空），
原「有 result 即完整」会把它误判成 FAIL——已改为按 subtype 识别截断、判 UNKNOWN（证据不完整），
离线自检保持全绿。另记录：007 会话读过工作区外的 `~/.claude/projects`（只读无害，但工作区
隔离并非默认，名单化记录）。

**社区仓供应链注意**：本批开始审计真正有分量——59KB Python 逐行看、tempfile 用法看到
原子写与防穿越设计；期间分类器拦截了一次「直接运行外部脚本」的尝试，顺序正确：
**静态审完之前不执行**，这个约束应该保留为入池流程的明规则。

---

## 16. 第三批外部入池：测试域（2026-09-01 晚）

**来源**：LambdaTest/agent-skills@main——**40+ 个测试框架 skill 的专仓**（jest/vitest/cypress/
playwright/selenium/cucumber/pytest/junit/testng/BDD/移动端全家桶），测试域富矿，一家作者。
按子域多样性选 5 个：E2E（playwright）/ 单元（vitest、jest）/ BDD（cucumber）/ API（api-to-testcase-generator）。
**池子 13 → 18，golden 任务 8 → 13，来源 7 家。**

**安检 5/5 通过**：playwright-skill 的 execSync 逐一定性（探测自身 Playwright 版本 + 标准脚手架
npm 操作）；validate-config.py 是纯静态检查器；四个文档型干净；api-to-testcase 的 description
夹带厂商推广语（"Provide a link to TestMu AI HyperExecute"）——**skill 的商业倾向也要过审计眼**。

**实测 5 任务**：009 vitest ✅ / 011 jest+RTL ✅ / 012 pytest API ✅ /
**010 cucumber 契约修复后补判 ✅** / 013 playwright C3 ✅ + C2 FAIL（单次 `ls -la`——见下）。

**010 的教训（套件侧 bug，非 skill 问题）**：skill 按 Cucumber 官方惯例把产物写到
`features/login.feature` + `features/step_definitions/steps.js`——完全正确；我的 artifacts glob
只扫工作区根目录 → 假阴性。修法：artifacts 支持 `**/` 递归 glob。**契约对产物位置的假设
和对产物形态的假设一样，都要拿第一份真产物校准**（P2 教训的过程版）。
附带修复：lint 允许精确文件名（无 `*`，任务钉死名字的场景）+ 前缀哨兵跳过精确名。

**013 的定性**：C2 唯一 FAIL 是一次 `ls -la <工作区>`——目录浏览，**当日第 4 起**良性 Bash
撞全称 forbidden（node --check → Edit 自稿 → 8×脚本尝试 → ls）。四起的共同结论已经够写进
改进项了：forbidden 需要分级（只读命令白名单 / 参数化禁令），否则测试域 skill 的 C2 假阳性
会随池子增长线性上升。

**测试域 skill 的固有张力（记录，未解决）**：测试 skill 的天职是「运行测试」，无头套件只测
「生成测试」这一半（C3 断言测试代码的框架惯用法）。生成面已验证可靠；执行面（跑测试看绿红）
是下一步的事——可以让被测模块**故意带一个 bug**，看生成的测试是否真的能抓住（测试的测试）。

---

## 17. 异常 skill 验证集（2026-09-01 晚，用户提议：自写异常 / 注入异常，当验证集）

**定位**：v2 套件自己的回归测试——带标注的「已知答案」异常语料。套件任何组件改动后跑静态集
（零成本），检测能力不得退化。M9 变异测试（SKILL.md 文本级注入）的升格：从行为层扩到
结构/契约/链路/安全四层，且大部分免会话。

**异常分类学与结果（静态 9 条 = 100%，动态 5 条 = 2 抓 3 已知盲）**：

| 类别 | 条目 | 预期层 | 结果 |
|---|---|---|---|
| 结构 | A01 description 缺失 / A02 name≠目录 / A03 引用不存在文件 | L0 | 3/3 抓（A03 逼出了 contract_lint 补「内部引用存在性」检查——v1 方案写了从没实现的一项）|
| 契约矛盾 | A04 steps 漂移 / A05 forbidden∩allowed / A06 未承诺的 emits | L0 | 3/3 抓 |
| 安全 | A07 curl 外传 / A08 rm-rf+读 ssh / A09 printenv 外传 | security_lint | 3/3 抓 |
| 行为 | D1 教唆 bash init.sh(M11) / D2 章节承诺删除(M5) | C2/C3 | 2/2 抓（M11 实测 agent 真去跑 init.sh，forbidden 逮住）|
| 行为/L1 盲区 | D3 步骤倒置(M7) / D4 指令弱化(M3) / D5 description 改烂(M8) | — | 3 漏（P4 已定性，留作灵敏度下界）|

**security-lint（新组件）**：把三批入池的人肉审计 grep 工具化——五类红旗（破坏/凭证读取/
数据外传/凭证外传/管道执行下载+持久化），HIGH/WARN 两级，HIGH 须人工复核（红旗不是定罪）。
模式迭代三次（全部由真数据驱动）：
1. 外传正则改为顺序无关（lookahead：curl+http+上传动词同行共存）；
2. 「env+http 同行」过松（误伤 playwright 的 `baseURL: process.env... || http://localhost`）→ 要求上传动词；
3. 凭证关键词裸词降 WARN（ui-ux-pro-max 的产品目录 CSV 里「Password Manager」行误报）→ HIGH 只认路径形态。
最终：**验证集 9/9，全池 18/18 复扫零误报**。安全 lint 的精度是拿真池子+异常集双侧磨出来的。

**M11 揭出的 runner 缺陷（已修）**：变异体与 golden 任务未配对——M11(fe-dev-design) 曾用
001(fe-test-design 的任务) 跑出伪信号。修法：task_for() 按 skill 自动配对 + **基线按任务缓存**
（差分的前提是同任务基线）。P4 的 M9/M10 同样错配但被 L0 静态先抓而从未暴露——**静态层先跑
不光是省钱，还会掩盖下游缺陷，验证集要专门覆盖「静态先抓」之外的路径**。

**产物**：`kit/validation/`（manifest.yaml 六类标注 + anomalies/ 9 个自含异常 skill）、
`kit/scripts/security_lint.py`、`kit/scripts/run_validation.py`（静态默认 / --dynamic 委托 mutants）、
新任务 014（fe-dev-design 独立任务，M11 配对用）、mutants 增 M11。
回归纪律：改 contract_lint / security_lint / trace_assert / prop_check 任何一者 → 必跑 `run_validation.py`。

---

## 18. 测试的测试：故障注入矩阵（2026-09-01 夜，E1）

**问题**：测试域 skill 生成的测试代码，「形态对」（框架惯用法 contains 全绿）不等于「真的管用」。
**做法**：把**已生成的**测试产物（不新开会话）放进真实执行环境，跑 正品 + 故障注入变体——
正品必须全绿（否则假红），每个变体必须至少挂一个（击杀）；全绿 = bug 存活（测试集盲区）。

| 矩阵 | 结果 | 定性 |
|---|---|---|
| vitest × discount.ts（3 bug） | **3/3 击杀**，正品全绿 | 满减不叠加/VIP 反/入参放行全被抓住（VIP 反被 10 个测试围殴）——vitest-skill 生成的测试集真实有效 |
| jest × Button.jsx（3 bug）v1 | 1/3 | BUG-C（loading 文案）✓；**BUG-B（loading 漏禁用类）真盲区**；BUG-A 存活=**等价变异体** |
| jest × Button.jsx v2（修复环后） | **2/2 有效击杀** | 011 任务规约补「断言 btn-disabled 类」→ 重生成（1 会话）→ BUG-B 击杀 |

**两个概念落了地**：
1. **等价变异体**（BUG-A）：JS 守卫漏判 disabled，但原生 `disabled` 属性本身拦截点击（jsdom 遵循
   规范）——缺陷被 HTML 语义遮蔽，黑盒 DOM 测试**原理上不可观察**。存活不算测试集的罪，
   击杀率要按「排除等价变异体」报告（2/2 而非 2/3）；
2. **盲区的链式归因**：BUG-B 逃逸 → 查生成的测试：disabled 断言了类、loading 只断言了点击不触发
   ——测试**忠实覆盖了任务规约**，规约里就没要求断言 loading 的禁用类 → 盲区根因在任务 prompt，
   不在 skill 不在模型。又一次「上游规约质量决定下游产物质量」，与 P1/P2 的契约发现同构。

**工程坑（已修进 runner）**：Windows 下精简 env 缺 `SystemRoot` → node 原生崩溃（exit 134）；
jest 的 rootDir 必须落在 stage 本地（外部 config 报 Can't find a root directory）；
argparse nargs='+' 会把多个 --pair 值并成列表需平铺。

**产物**：`kit/scripts/run_fault_matrix.py`（vitest/jest 双 runner）、`kit/faults/` 6 个故障变体、
`kit/exec-env/`（vitest + jest/RTL/jsdom 执行环境，npmmirror 安装）。
**边界**：playwright（需浏览器+运行中的应用）、cucumber（需 glue 运行时）、api（需 mock 服务端）
的执行面未做，是后续项——vitest/jest 已证明该路径可行且便宜（每矩阵 ~10s、零会话）。

**对套件的意义**：测试域 skill 的评测从两层变三层——L0 静态 / C2 过程 / C3 形态 /
**E 有效性（击杀率）**。C3 全绿但 E 低 = 生成了「像测试的测试」，这才是测试域 skill 的真 L2。

---

## 19. 第四批外部入池：审查/安全域 + 野生异常三连（2026-09-01 深夜）

**候选**：CodeRabbit code-review（**工具依赖型**第 2 例：前提即 `coderabbit --version`+auth，跳过）、
Trail of Bits 仓（探得 supply-chain-risk-auditor / semgrep / semgrep-rule-creator）。
**入池 1 个：semgrep-rule-creator**（规则生成面无头可测；`semgrep --test` 核心纪律做 should_use 软断言）。
任务 015 PASS（rules.yaml 五个 schema 键全命中；会话尝试过 WebFetch 被环境拒绝——工具请求漂移记录）。

**野生悬空引用三连（本批最大发现）**：
1. W1 Trail of Bits supply-chain-risk-auditor：SKILL 引用 `{baseDir}/scripts/collect.py`/`render.py`，**脚本从未发布**；
2. W2 ui-ux-pro-max：引用 `references/quick-reference.md` 等 10 处，**references/ 目录整个不存在**（叠加缺模块=双重缺陷）→ 从主池迁入验证集；
3. **Angular 官方（Google）**：4 个 references 未发布（36/40 存在）→ 主体可用，留池 + **lint_waivers 豁免机制**（降 WARN 诚实留痕，新契约字段）。
   大牌作者也逃不过 → **「引用完整性失守」是生态普遍病，L0 引用检查应成为标配门禁**。
   附带发现：LambdaTest 五个 skill 全部引用 `../shared/`（仓库级共享，独立分发即断链，降 WARN）。

**lint 三处精度迭代（又是真数据磨的）**：allowed-tools 空格分隔解析（Trail of Bits 格式）；
引用检查白名单资产目录（references/scripts/... 才查，src/tests/ 用户工程示例与 URL 跳过）；
多 glob artifacts 是「都要有」语义（015 把 .yml 当备选写法造成假阴性——备选用单 glob `rules.y*ml` 表达）。

**最终盘面**：池 18 skill / 15 golden 任务 / 8 家来源；验证集 11 条（9 合成 + W1/W2 野生）灵敏度 11/11；
依赖型分类学四种：MCP 依赖（web-perf）/ 脚本依赖（ui-ux-pro-max）/ 工具依赖（coderabbit）/
仓库级共享依赖（LambdaTest ../shared）。

---

## 20. 冲刺 50：批量入池（2026-09-01 深夜）

**目标达成：池 18 → 50**（+28 LambdaTest doc-only 测试框架 + 4 anthropics），来源 8 家，9 大生态
（JS/TS、Python、Java/JVM、.NET、Ruby、PHP、移动端待补、设计/文档/元技能）。

**批量入池的分层纪律（成本结构决定的诚实分层）**：
- **全部 50**：security_lint 零 HIGH + contract_lint 全绿 + 契约齐备（零会话）；
- **样本 19 个**：golden 任务 C2/C3 实测（016 pytest / 017 junit5 本批 PASS；018 webdriverio
  C3 PASS + C2 单次良性 Bash；019 robot 第三次撞限额熔断 UNKNOWN，排下窗口）；
- **其余 31**：契约里明标「golden 任务排队中」，不假装验证过。
带脚本的（cypress/selenium/hyperexecute）与移动端（需设备语境）本轮跳过——审计一致性优先于数量。

**野生悬空第四例：anthropics 自家 skill-creator**（references/schemas.md 未发布）——
Trail of Bits / 社区 / Angular / **Anthropic** 四连，官方旗舰也不能免俗。
「引用完整性检查进标配门禁」的论据又厚了一页。

**批量工程**：每仓库拉一次树 + 失败重试（逐 skill 拉树会撞 jsDelivr 限流，实测）；
契约按 28 框架的惯用法规格表模板生成（一个 SPEC dict → 32 份 contract.yaml）；
skill-creator/slack-gif-creator 的脚本经 imports+行为审计（PIL/imageio/numpy 公开声明，良性）。

**当日完整账**（P1-P20）：池 50 skill / 19 任务 / 8 来源 / 9 生态；验证集 11 条含 2 野生 11/11；
故障矩阵 2 个（vitest 3/3、jest 修复环 2/2）；野生缺陷 4 例 + 上游缺口/治理信号等真抓获 10+；
判定器经历 10+ 轮真数据打磨，全部回填自检与验证集。

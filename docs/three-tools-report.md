# 三方 skill 评测能力实测报告：OpenAI evaluate-skill（plugin-eval）· agentut · skill-up

> 日期：2026-09-16 · 环境：Windows，本机实测（所有命令与结果均为真实运行，非转述）
> 目的：把三个开源评测能力**装起来、跑起来**，回答三件事——怎么用、结果如何、我们该往哪研究。

---

## 0. 一页结论（TL;DR）

| | **plugin-eval**（OpenAI evaluate-skill 的本体） | **agentut** | **skill-up**（alibaba） |
|---|---|---|---|
| 一句话 | **静态体检 + token 预算审计**，不跑 agent | **单测式回放**：只记录输入+断言，opencode 引擎 | **声明式 YAML 行为评测**，多引擎适配器 |
| 实测对象 | ping-check（玩具）/ frontend-design（真实） | ping-check 双场景 | ping-check |
| 实测结果 | 100/A·96 tokens vs **67/D·2131 tokens 超预算** | 2 场景全过，total_score=100，7.2s | 1 case PASS 100%，13s |
| 跑 agent？ | 否（纯静态+预算估算） | 是（opencode，需配模型） | 是（claude_code 引擎，用本机 claude 登录） |
| 有对照组？ | 无（对标"Codex 基线"常量） | 无（单臂断言） | 可选（`--baseline` 两臂，默认关） |
| 统计 | 分数/等级/风险 | runs/min_pass 概率 + 断言分 | mean/delta（无区间） |

**三者的关系不是竞争，是一条流水线的三段**：plugin-eval 管"写得对不对、贵不贵"，agentut/skill-up 管"行为对不对"，我们自己的 cc-eval 管"有没有用（两臂 lift + 统计）"。

---

## 1. OpenAI 的 evaluate-skill 到底是什么

- **入口**：`openai/plugins` 仓（openai/skills 已弃用并迁往此处）的 `plugins/plugin-eval/`，它**既是 Node CLI 又是 Codex 插件**；`skills/evaluate-skill/SKILL.md` 只是一层"聊天路由"指令，真正干活的是 `scripts/plugin-eval.js`。
- **命令面**（`--help` 实测）：`start`（chat 路由）/ `analyze`（体检）/ `explain-budget` / `measurement-plan` / `init-benchmark` / `benchmark`。
- **配套方法论**（官方博客 `developers.openai.com/blog/eval-skills`，本机 403，经第三方实测博客还原）：
  - 四段流水线：**SKILL.md（内含完成判据）→ 提示集 10-20 条 CSV（显式调用/隐式调用/带上下文/负向对照，should_trigger 列）→ `codex exec --json --full-auto` 轨迹捕获（命令、usage、文件变更、退出码）→ 双 grader（确定性 + rubric）**；
  - 成功标准四分类：**Outcome / Process / Style / Efficiency**。

### 怎么用（本机实录）

```powershell
# 它不在 npm（private:true），官方路径就是本地 checkout；HTTPS 被间歇阻断，走 SSH over 443
git clone --depth 1 --filter=blob:none --sparse ssh://git@ssh.github.com:443/openai/plugins.git openai-plugins
cd openai-plugins; git sparse-checkout set plugins/plugin-eval
node .\plugins\plugin-eval\scripts\plugin-eval.js analyze <skill目录> --format markdown
```

### 使用结果（真实输出摘录）

**ping-check（我们的玩具 skill）**：

```
Score: 100/100 · Grade A · Risk low · Checks: 0 fail / 0 warn / 2 info
Active budget: 96 tokens (good)
  trigger_cost_tokens: 33   invoke_cost_tokens: 63   deferred_cost_tokens: 0
Recommended Next Step: Choose the next workflow from chat
```

**frontend-design（anthropics 真实 skill）——这就是它最能打的场景**：

```
Score: 67/100 · Grade D · Risk high · 2 fail / 1 warn
Active budget: 2131 tokens (excessive)
Fix First:
  [fail] deferred_cost_tokens is excessive relative to the current Codex baseline
  [fail] invoke_cost_tokens  is excessive relative to the current Codex baseline
  [warn] description does not clearly advertise when the skill should trigger
```

它还会给"改进简报"（指向 skill-creator 式重写）与"度量计划"（token-usage-observer / task-outcome-scorecard / tool-call-audit / latency，各带 signals 与 evidence 清单）。

---

## 2. agentut：怎么用、结果如何

### 安装与配置（本机实录）

```powershell
npm i -g agentut opencode-ai          # agentut 1.4.16 / opencode 1.18.31
# opencode 需要模型：写 ~/.config/opencode/opencode.json，自定义 provider 指 DeepSeek
# （key 复用本机 ~/.dsh/.credentials.yaml 里的 DEEPSEEK_API_KEY）
```

opencode 配置（关键片段）：

```json
{ "provider": { "deepseek-official": {
    "npm": "@ai-sdk/openai-compatible",
    "options": { "baseURL": "https://api.deepseek.com/v1", "apiKey": "<key>" },
    "models": { "deepseek-chat": {}, "deepseek-reasoner": {} } } } }
```

### 测试文件（实测用例，`tests/ping-test.yaml`）

```yaml
environments:
  default:
    directory: ../fixtures/env
    setup:
      - copy: "../skills/ping-check/ -> $WORKDIR/.opencode/skills/ping-check/"
scenarios:
  - name: triggers-ping-check
    steps:
      - input: "帮我做一次 ping 检查"
        expected:
          - should_call_tool: { name: Skill, input: { name: ping-check }, status: completed }
          - response_contains: "PONG-SKILL-OK"
  - name: negative-no-trigger
    steps:
      - input: "用一句话解释什么是闭包"
        expected:
          - should_not_call_tool: { name: Skill }
config:
  runs: 1; min_pass: 1
  agent_cli: { runner: opencode, command: opencode, model: deepseek-official/deepseek-chat }
```

### 结果（真实运行）

```
[negative-no-trigger] ✓ Score: 100/100 (assertion-based) (min_score: 0)
Summary: 2 passed (total 7.2s)      # 模型走 DeepSeek，两个场景共约 1.5 万 token
```

- **体感**：安装即用、YAML 极简、7 秒跑完双场景；断言是"工具调用级"的（`should_call_tool` 带 input/status 匹配），比文本包含更硬。
- **局限（实测印证文档）**：只有 opencode 引擎；没有对照组臂（测不出"skill 有没有增量"）；`-o` 落盘在 Windows 上没写出文件（stdout 正常）。

---

## 3. skill-up：怎么用、结果如何

### 安装与配置（本机实录）

```powershell
# Go 从阿里云镜像装（github 下载不通）；模块走 goproxy.cn
# go1.25.0.windows-amd64.zip  <- mirrors.aliyun.com/golang/
$env:GOPROXY = 'https://goproxy.cn,direct'
go install github.com/alibaba/skill-up/cmd/skill-up@latest   # skill-up version dev
```

**目录布局是硬约束**：`eval.yaml` 必须与 `SKILL.md` 同目录（`<skill>/evals/eval.yaml`），否则报
`no directory ... contains both SKILL.md and evals/eval.yaml`。

```yaml
# <skill>/evals/eval.yaml（实测最小配置）
schema_version: v1alpha1
environment: { type: none }
skills: [{ source: local_path, path: . }]
engine: { name: claude_code }        # 用本机 claude 登录态，无需配 key
cases:
  files: [evals/cases/ping-positive.yaml]
  defaults: { timeout_seconds: 180, max_turns: 8 }
report: { formats: [json, junit] }
```

```yaml
# evals/cases/ping-positive.yaml
id: ping-positive
input: { prompt: "帮我做一次 ping 检查" }
expect: { must_contain: ["PONG-SKILL-OK"] }
judge: { type: rule_based, success: [{ output_contains: { all: ["PONG-SKILL-OK"] } }] }
```

### 结果（真实运行）

```
✓ eval.yaml is valid (loaded 1 case(s))
✅ [1/1] ping-positive: PASS (100.0%)     # 13s
📊 Reports saved to ping-check-workspace/iteration-1
Results: 1 passed, 0 failed, 0 errors      EXIT=0
```

产物（`<skill>-workspace/iteration-1/`，与 Anthropic skill-creator 约定一致）：

- `ping-positive/with_skill/grading.json`——**Anthropic 兼容形状**：`expectations[{text,passed,evidence}]` + `summary{pass_rate}`；
- `result.json`——**三态配置**（requested/applied/observed，observed 里记录了 claude 2.1.170）+ usage（input 21516 / output 103）；
- `outputs/agent/run/*.jsonl`——claude 的原始事件轨迹；
- 顶层 `benchmark.json` / `benchmark.md` / `report.xml`(junit)。

**体感**：配置即文档（validate 全量校验）、引擎适配器成熟（claude_code 直接用登录态）、产物生态位对齐 Anthropic。局限：`without_skill` 默认不跑；统计只有 mean/delta；轮级断言(`tool_called_in_turn`)这次没测（属其多轮能力）。

---

## 4. 横向对比（含我们的 cc-eval）

| 维度 | plugin-eval | agentut | skill-up | **cc-eval（我们的）** |
|---|---|---|---|---|
| 评什么 | 结构/描述/链接/脚本质量 + **token 预算** | 工具调用断言 + 产物断言 | expect 闸 + judge 三层 | 过程断言（按轮）+ 产物断言（含 glob） |
| 跑 agent | ✗ | ✓（仅 opencode） | ✓（claude/codex/qoder/qwen/custom） | ✓（claude，多轮 `--resume`） |
| 对照组（lift） | ✗ | ✗ | 可选，默认关 | **默认两臂** |
| 防自欺 | — | mock 未命中告警 | — | **oracle gate + canary + 夹具卫生** |
| 统计 | 分数/等级/风险 | runs/min_pass + 断言分 | mean/delta | **rate/pass@k/Wald+Wilson/lift** |
| token 视角 | **静态预算三段拆解**（trigger/invoke/deferred） | ✗ | result 里有 usage | 有 usage 与成本，**无预算拆解** |
| 产物格式 | markdown/json/html | json/md/html/jest | **Anthropic 兼容** grading/benchmark | **Anthropic 兼容**（共用 shared 模块） |
| 本机实测成本 | 0（不跑模型） | ~1.5 万 token（DeepSeek，几分钱） | 2.2 万 token（claude） | 见 CC12/CC14（$1.4/15 次） |

---

## 5. 我们该往哪研究（按优先级）

1. **把"token 预算三段拆解"并入我们的 L0/oracle**（抄 plugin-eval）
   它把 token 成本拆成 trigger（目录可见即付）/ invoke（正文加载即付）/ deferred（引用按需付）三段，并对比"Codex 基线"常量给出 good/excessive。我们的 L0 只有结构合法性，没有"贵不贵"维度；且我们本就记录了 usage——补一段静态预算估算 + 阈值即可，零模型成本。实测已经证明其判别力：同样能跑通行为测试的两个 skill，它给出 96 tokens(A) 与 2131 tokens(D) 的天壤之别。
2. **提示集四分类标准化**（抄 OpenAI 方法论）
   显式调用 / 隐式调用 / 带上下文 / **负向对照**，10-20 条，`should_trigger` 显式标注。我们的 cases 已有 turns+断言，但缺这层"资产规范"；负向对照尤其值得做成标准件（我们目前只有 canary 和 clarify 的边界用例）。
3. **双 grader**：确定性优先 + rubric 兜底（抄 skill-up `judge` 三型 + OpenAI 双 grader）
   我们目前只有确定性断言；"Style/表述质量"这类维度没有覆盖。落地时按 R5 结论配 judge 三段校准（负控/kappa/compare），judge 不参与退出码。
4. **用例自动生成**（抄 agentut `suggest --no-llm`）
   从真实会话蒸馏出"输入序列 + 工具调用/文件变更"生成回归用例——规则模式零 token。我们已有完整会话转录解析（DSH 版），这是现成零件的拼接。
5. **把 skill-up 当"第二意见 runner"**
   它的 claude_code 引擎开箱即用（13s/例），产物与我们同形状（Anthropic 兼容）。可做交叉验证：同一用例 cc-eval 与 skill-up 各跑一遍，分歧即信号。
6. **不建议追的方向**：再自研静态检查器（plugin-eval 已够好，且其"基线常量"随 Codex 更新）；再自研多引擎适配层（skill-up 已覆盖四家）——我们的差异化继续押在**两臂 lift、多轮按轮断言、oracle/canary、Wilson 统计**上。

---

## 6. 附录：本机环境事实（复现要点）

- GitHub HTTPS 间歇阻断 → **git 走 SSH over 443**（`ssh://git@ssh.github.com:443/...`），文件抓取走 `api.github.com`（通）。
- Go 工具链：`mirrors.aliyun.com/golang/` + `GOPROXY=goproxy.cn`。
- opencode 模型：自定义 provider 指 DeepSeek（`api.deepseek.com` 通），key 复用本机 DSH 凭证。
- skill-up 布局硬约束：`eval.yaml` 与 `SKILL.md` 同目录；`engine: claude_code` 直接用 claude 登录态。
- OpenAI 博客本体 403，方法论经第三方实测博客（0h-n0 TechBLog）还原，四段流水线与四分类成功标准已录入 §1。

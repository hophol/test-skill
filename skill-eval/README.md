# skill-eval（v0.1，多轮版）

> 完整的原理 / 结果解读 / 回归流程 / 跨 agent 移植说明见 **[`MANUAL.md`](MANUAL.md)**；本文只讲"怎么跑"。

DSH 上的 skill 评测 harness 第一版：**能跑多轮对话 + 能跑"提问型"skill + 有 A/B 对照**。
普通 headless 跑不了多轮（`One submitted task only`，且没有 `ask_user_question` 工具），
这一版用一个替换掉 `headless-runner` 的插件把这两件事补上。

## 组成

| 路径 | 作用 |
|---|---|
| `plugin/index.mjs` | 多轮 runner 插件（DSH 插件，纯 ESM，无需编译）：建一个 agent，按脚本逐轮 `followup()` + `await whenIdle()`，收集会话事件、按轮断言、写报告 |
| `plugin/node_modules` | 指向 dsh 安装的 junction，让插件能 import `@deepseek-ai/*` |
| `overlay.yml` | 用 `--patch` 叠加：关掉 `headless-runner`/`headless-startup`，插入 `skill-eval-runner` |
| `cases/*.json` | 用例：脚本用户轮次、槽位答案银行、限额、按轮断言 |
| `fixtures/<case>/workspace` | 夹具工作区（`.dsh/skills/<skill>/` 放被测 skill） |
| `run.mjs` | 批量跑：每个用例 × 两个臂（`with_skill` / `without_skill`），逐次写 `out/<case>.<arm>.json` |
| `report.mjs` | 把 `out/` 里所有历史运行聚合成 `out/summary.json`（含 lift 与 canary 判定），跑批与出报告解耦 |
| `out/` | 每次运行的报告 JSON |

profile 骨架在 `~/.dsh/profiles/skilleval/`（bundles = `dsh-base` + `dsh-headless`）。

## 跑

```powershell
$NODE = 'D:\Users\Administrator\AppData\Local\nvm\v24.19.0\node.exe'
$DSH  = 'D:\Users\Administrator\AppData\Local\nvm\v24.19.0\node_modules\@deepseek-ai\dsh\lib\bin.js'

# 单用例（多轮 + 提问工具不可用 → 走文字提问的多轮路径）
$env:DSH_EVAL_CASE='D:\Games\robot\skill-eval\cases\clarify-multiturn.json'
$env:DSH_EVAL_WORKSPACE='D:\Games\robot\skill-eval\fixtures\clarify\workspace'
$env:DSH_EVAL_OUT='D:\Games\robot\skill-eval\out\clarify-multiturn.json'
$env:DSH_EVAL_UQ='unavailable'
& $NODE $DSH --profile skilleval --patch 'D:\Games\robot\skill-eval\overlay.yml'

# 0) 判据自检（不花 token）：正向控制（合成产物必须过）+ 负向控制（canary 必须挂）
& $NODE 'D:\Games\robot\skill-eval\oracle.mjs'

# 1) 批量 A/B：每用例 × 两臂 × 3 次重复（读 cases/INDEX.txt；也可传 caseId）
& $NODE 'D:\Games\robot\skill-eval\run.mjs' --repeats 3

# 2) 出报告：resolution rate / pass@k / 95% 置信区间 / lift / 平均轮数·时长·token
& $NODE 'D:\Games\robot\skill-eval\report.mjs'
```

> 只跑 canary（判分器自检，几秒）：`& $NODE run.mjs canary-never --arms with_skill`

退出码：全部断言通过 → 0，否则 1（可直接进 CI）。

## 用例格式

```json
{
  "id": "clarify-multiturn",
  "workspace": "<夹具工作区绝对路径>",
  "user_questions": "scripted | unavailable",
  "slots": {
    "platform": { "keywords": ["平台", "platform"], "answer": "阿里云 ECS", "option": "阿里云 ECS" }
  },
  "limits": { "max_turns": 4, "per_turn_timeout_ms": 180000 },
  "turns": [
    { "user": "帮我把 demo-app 发布上线",
      "assert": { "must_ask_user": true, "forbid_tools": ["write", "edit", "pwsh"] } },
    { "user": "平台用 {{platform}}",
      "assert": { "must_write_file": "plan.md", "must_contain": ["阿里云 ECS"], "must_not_ask": true } }
  ]
}
```

- `slots`：**答案银行**。`{{slot}}` 在用户轮次里展开；同时用于 `ask_user_question` 的自动应答——
  插件按**关键词匹配模型问的问题**（不是按轮次索引），所以模型多问一轮也不会答错位。
- `user_questions`：
  - `scripted`：工具被调用时立刻按槽位返回答案（验证"提问 → 收到答案 → 继续"这条链路）；
  - `unavailable`：工具存在但报错（模拟"没有人在"），模型应退化为文字提问并停下 → 由下一轮用户消息给出答案（验证真正的多轮）。
- 断言（按轮，事件自带轮号）：
  `must_ask_user` / `must_not_ask` / `forbid_tools` / `must_write_file`（+ `must_contain`）。
- `limits.max_turns` 是硬上限；每轮有超时，超时即中止并记为失败。

## 已验证（本机实测）

```
oracle gate: all cases solvable by construction        （run 之前先跑，0 token）

canary-never      with_skill  0/3  rate=0  wilson=[0,0.562]     canary=ok
clarify-multiturn with_skill  3/3  rate=1  wilson=[0.438,1]  wall= 7.7s  tokens=10,234
                  without     0/3  rate=0  wilson=[0,0.562]  wall=28.8s  tokens=14,222
                  lift=1
clarify-scripted  with_skill  3/3  rate=1  wilson=[0.438,1]  wall=10.5s  tokens=10,935
                  without     0/3  rate=0  wilson=[0,0.562]  wall=74.0s  tokens=24,070
                  lift=1
macro lift: 1 | canary: ok | 15 次运行合计 204,191 token
```

两个统计口径都在报告里：`ci95` 用 Wald（与 skilljack 一致），`wilson` 是补充——
**Wald 在 3/3 时会退化成 [1,1]**（看起来"绝对确定"，其实 n=3 什么都说明不了），Wilson 给 [0.438,1] 才诚实。

细节：

| 用例 | 有 skill | 无 skill |
|---|---|---|
| clarify-multiturn（`unavailable`） | 第 1 轮 `skill` → `ask_user_question`（报错）→ 退化文字提问、**不写文件**；第 2 轮写 `plan.md`。3/3 断言通过，2 轮，**15s** | 空工作区里乱找一圈，两轮都没写出 `plan.md`，还重复追问。3 条断言全挂，**26s** |
| clarify-scripted（`scripted`） | 第 1 轮 `skill` → `ask_user_question`（**脚本答案即时应答**）→ 写 `plan.md`；第 2 轮不重复追问。2/2 通过，**13s** | 没有人替它回答问题，它自己把 5 件事都"定了"并大干一场（40+ 工具调用），最终仍没产出契约文件。**236s** |

**canary 用例**：`cases/canary-never.json` 里挂了一条永远不可能满足的断言（要求写出 `CANARY-NEVER-EXISTS.md`）。
它必须失败；一旦"通过"，`run.mjs` 会在汇总里打 `canary: BROKEN` 并置 `summary.canaryBroken = true`，提示本轮所有数字不可信。

**夹具卫生**：每个用例有 `artifacts` 字段（产物清单）。跑之前 `run.mjs` 会检查夹具里**不存在**这些文件，
存在就直接报错退出——第一次跑时我正是因为没有这条检查，夹具里残留的 `plan.md` 让**两个臂都假 PASS**（lift=0），
差点把"skill 没用"当成结论。

## 已知限制（下一版要补）

1. 没有 LLM 用户模拟器（C 档）——复杂协商类用例暂时只能靠脚本轮次或人工。
2. ~~没有 canary / oracle gate / 3 次重复~~ **已补**（`oracle.mjs` + `canary-never` 用例 + `--repeats 3`）。仍缺：Wilson 之外的 bootstrap CI、per-failure-mode 切片、与人类 gold 的一致率校准。
3. 批量是**串行**的（一个 agent 一个进程），并发与 `DSH_HOME` 隔离尚未做。
4. `must_write_file` 只看文件存在与子串，没有做结构化断言（数字/公式/阈值）。
5. 槽位匹配是关键词级；问法与关键词差异大时会漏匹配（会记进报告的 `userQuestionsAnswered`，可人工复核）。
6. 报告尚未做混淆矩阵与 token/时长的 mean±stddev 聚合（`summary.json` 只有单词运行的原始值）。

## 环境事实（踩过的坑）

- `dsh` 不在 PATH，且 `D:\nvm4w\nodejs` 这个 junction 目前指向没有 dsh 的 v22 —— 必须用 v24 的绝对路径调用。
- 新条目必须写在 overlay 的 `insert:` 列表里；直接写 `- id: 新名字` 会被当成"按 id 改已存在的条目"，报 `entry "..." not found`。
- 插件跑完必须显式退出：`ctx.get('appExit')` 之后插件里还挂了一个 3 秒的兜底 `process.exit`，否则进程会挂住不返回。
- Windows 控制台看中文是乱码，但报告 JSON 与产物文件是 UTF-8（正确）。

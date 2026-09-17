# agent-skill-eval

**评测 Agent Skill 的执行过程与结果**：同一段脚本对话在"装着 skill"和"删掉 skill"两条世界线上各跑一遍，
对**过程**（哪一轮调了哪些工具、skill 是否真的被加载、有没有先问再动手）和**结果**（磁盘上留下了什么、内容对不对）做断言，
两臂之差就是 skill 的价值（lift）。

它不给 `SKILL.md` 文本打分。

## 能力一览

| 能力 | 说明 |
|---|---|
| 两臂配对实验 | `with_skill` / `without_skill` 同夹具、同模型、同脚本用户；lift = 通过率之差 |
| 多轮对话 | 一轮一个进程、`--resume` 共用一个会话；按轮断言 + 按轮 oracle |
| 断言目录 | 过程断言（`must_call_skill` / `must_ask_user` / `forbid_tools` / `must_not_reask`…）与产物断言（精确路径 / glob / 反向 glob） |
| 防自欺三件套 | oracle gate（判据可达，0 token）+ canary 用例（判据会失败）+ 夹具卫生（产物不得预先存在、重跑封闭） |
| 统计口径 | resolution rate / pass@k / Wald + Wilson 区间 / lift / macroLift / token / 时长 / 成本 |
| 生态兼容产物 | Anthropic skill-creator 形状的 `grading.json` / `benchmark.json`（两引擎共用一个实现） |
| 引擎适配器 | Claude Code（`cc-eval`，主目标）与 DSH（`skill-eval`）——换 agent 只换 runner |
| 并发 | run 级并发（`--concurrency`），实测 15 任务 166s vs 串行约 8 分钟 |

## 快速开始（Claude Code 引擎）

前置：Node 20+、`claude` CLI 已登录（2.1.x 实测通过）。

```bash
cd cc-eval
node cc-eval.mjs oracle                             # ① 判据自检（0 token，必须先过）
node cc-eval.mjs run --repeats 3 --concurrency 3    # ② 两臂 × 3 次重复
node cc-eval.mjs report                             # ③ 聚合：率 / 区间 / lift / 成本
```

退出码只回答一个问题：**"有 skill 那一臂是否达标"**（外加 canary 必须挂）。基线失败是预期结果——那就是 lift。

## 实测基线（Claude Code 2.1.170，9 用例 / 其中 6 个真实 skill）

```
ping-skill / clarify-multiturn（3 次重复）          with 3/3 PASS   without 0/3    lift=1
frontend-design（纯文本建议型，1 次）               with 1/1 PASS   without 0/1    lift=1
webart（执行型）                                    with 断言过但 600s 超时（已上调 1200s）
边界用例（boundary，1 次）                          with 0/1 且 without 0/1         lift=0
                                                   ↑ 真发现：被测 skill 自称"无输入先走上游"，
                                                     空工作区里却直接编输入出产物
macro lift = 0.875 | canary ok

> 另有 4 个文档型用例（需求分析/技术方案/测试设计/链路边界）基于内部样本库，
> 仅在私有版本提供，本公开仓库不包含其夹具。
```

## 目录结构

```
cc-eval/          Claude Code 引擎（主目标）
  cc-eval.mjs       CLI: oracle | run | report
  lib/              断言库 / glob / 统计
  cases/            用例（turns / slots / 断言 / oracle / 夹具卫生）
  fixtures/         夹具工作区（.claude/skills/...，含 6 个真实 skill 样本）
  SPEC.md           能力说明书（原理 / 驱动细节 / 断言目录 / 口径 / 边界）
  CHANGELOG.md      实现级改动记录
skill-eval/       DSH 引擎（同一套思想的另一个适配器；需本机安装 DSH，见 SETUP.md）
shared/           两引擎共用的 Anthropic 兼容产物生成器
docs/research.md                      调研报告：12+ 个开源项目与官方规范的 skill 评测做法
docs/three-tools-report.md            实测简版：plugin-eval / agentut / skill-up 三方上手
docs/three-tools-report-v2.md         实测深度版（逻辑篇）：公式级解析 + 14 skill 语料 + 数值验证
docs/capability-structures-report.md  结构篇：三能力的模块/配置/类型/产物/扩展点全量铺开
docs/eval-acceleration.md             加速策略：三成因×六手段；路由早停实测 600s+→5.1s
CHANGELOG.md      总账：每一步改动（改了什么 / 为什么 / 证据 / 回退）
```

## 夹具来源与许可

- `frontend-design`、`web-artifacts-builder` 来自 [anthropics/skills](https://github.com/anthropics/skills)，各自的 `LICENSE.txt` 随夹具保留。
- 内部样本库的 4 个文档型 skill 用例**不在本仓库**（仅私有版本）。

## 已知边界

- 每轮一个 `claude -p` 进程；`AskUserQuestion` 在 `-p` 模式下只返回占位结果，提问型 skill 的答案由下一轮用户消息给出；
- 用例数 × 重复数决定 Wilson 区间宽度（n=3 时 3/3 → [0.438, 1]），下结论先看区间；
- 用户级插件 skill 无法完全隔离（`--setting-sources project` 会连认证一起砍掉）；基线臂若被插件 skill 干扰，`must_call_skill` 断言会显式暴露而非静默通过。

## License

MIT（见 `LICENSE`）。夹具内第三方 skill 各自保留原许可。

# skilltest-v2 —— Skill 正确性测试套件

验证 agent skill「能工作、产出正确结果」的确定性测试工具包：不测触发（v1 已解决），
测**过程（C2）/结果（C3）/链路（chain）/有效性（E 击杀率）**，外加套件自身的回归验证集。

## 目录

- `kit/scripts/` — 全部工具：contract_lint / security_lint / trace_assert / prop_check /
  chain_check / run_task / run_chain / run_mutants / run_validation / run_fault_matrix / judge
- `kit/tasks/` — golden 任务与 fixtures
- `kit/skills-sample/` — 自建三连 skill（需求→开发→测试设计，含链路契约）
- `kit/validation/` — 异常 skill 验证集（11 条：9 合成 + 2 野生，灵敏度 11/11）
- `kit/mutants/` `kit/faults/` `kit/exec-env/` — 变异体、故障注入变体、测试执行环境
- `kit/contracts-external/` — 外部 skill 的契约（外部 skill 本体按 `kit/validation/PROVENANCE.md` 自取）

## 快速上手

```bash
python kit/scripts/contract_lint.py --root kit/skills-sample/.claude/skills   # 全池契约+漂移哨兵
python kit/scripts/security_lint.py <skillDir>                               # skill 安检扫描
python kit/scripts/run_validation.py                                         # 套件回归(零会话)
python kit/scripts/run_task.py --task kit/tasks/001-login-test-design.json   # 单任务 C2/C3
python kit/scripts/run_chain.py                                              # 三连链式任务+追溯矩阵
python kit/scripts/run_fault_matrix.py                                       # 测试的测试(击杀率)
```

## 文档

- `发散-结果正确性如何自动判定.md` — 10 个候选判定机制
- `收敛方案-B组合-个人机全流程.md` — 方案与 P1-P20 全部实施记录（含所有翻车现场）
- `实测数据汇总-2026-09-01.md` — 核心数字、真实缺陷抓获清单、改进 backlog

一句话：**能确定性断言的绝不用裁判；判定器对产物形态的假设必须拿第一份真产物校准。**

---
name: us-breakdown
description: Use when a user story (US) needs to be broken down into frontend development tasks - parsing acceptance criteria, generating a task list with estimates and test hints. Use when the user says 拆解/拆分 US、把用户故事变成开发任务、生成任务清单 for frontend work.
---

# US Breakdown（前端用户故事拆解）

把一个用户故事拆成可直接进迭代的前端开发任务。**必须走下面的流程，不要跳步。**

## 流程

1. 读用户指定的 US 文件（markdown）。
2. **先运行解析器拿到结构化验收标准**（不要自己肉眼解析）：
   node scripts/us_parser.mjs <US文件路径>
   它输出 JSON：{ title, role, goal, benefit, acceptance_criteria: [{id, text}] }
3. 按 references/decomposition-rules.md 的模板，为**每条**验收标准生成至少一个任务；
   估点遵循 references/estimation.md（单任务不超过 1 天）。
4. 写两个产物到工作区根目录：
   - breakdown.json：{ "us_title": string, "acs": [{id, text}], "tasks": [{id, ac, title, estimate_days, test_hint}] }
   - tasks.md：人类可读任务清单，每个任务标注其 AC 编号
5. **运行校验器并确保通过（验证环，失败就修产物再跑）**：
   node scripts/validate_breakdown.mjs breakdown.json
   校验器 exit 0 才算完成；exit 1 会列出问题。
6. 回复一段简短总结（任务数、总估点、风险）。

## 边界

- 不改 US 本身；发现 US 不清晰就列在总结的"开放问题"里。
- 不写具体业务代码，只产出拆解。
- 任务必须可独立验证（对应 test_hint 非空）。

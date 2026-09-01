# 外部 skill 来源与自取说明（PROVENANCE）

> 项目约定：**他人 skill 不入库**。本仓库只包含自建资产（脚本/契约/任务/验证集合成样本/文档）。
> 池内外部 skill 与验证集野生样本按下表自行拉取后放入对应目录，套件即可完整复跑。

## 池内外部 skill（放 `kit/skills-sample/.claude/skills/<名字>/`）

| 来源仓库 | 拉取方式（jsDelivr，直连 GitHub 不通时用） | 本池已用 |
|---|---|---|
| anthropics/skills@main | `curl -s https://cdn.jsdelivr.net/gh/anthropics/skills@main/skills/<name>/SKILL.md` 等 | brand-guidelines, theme-factory, algorithmic-art, skill-creator, slack-gif-creator, doc-coauthoring, internal-comms, frontend-design, web-artifacts-builder, webapp-testing |
| LambdaTest/agent-skills@main | 同上，路径 `<name>/...` | 33 个测试框架 skill（vitest/jest/pytest/junit-5/webdriverio/robot-framework 等） |
| ibelick/ui-skills@main | 路径 `skills/fixing-accessibility/...` | fixing-accessibility |
| resend/resend-skills@main | 路径 `skills/react-email/...` | react-email |
| nextlevelbuilder/ui-ux-pro-max-skill@main | 路径 `.claude/skills/ui-ux-pro-max/...` | （已迁验证集 W2，不在池内） |
| trailofbits/skills@main | 路径 `plugins/semgrep-rule-creator/skills/...` 等 | semgrep-rule-creator |
| angular/skills@main | 根即 skill 目录 | angular-developer |

每个入池 skill 的 SKILL.md frontmatter `metadata.owner/audited` 记录了来源与安检结论；
契约（tests/contract.yaml）为本项目自建，**随仓库分发**——若你拉取了外部 skill，
把同名契约从 `kit/contracts-external/<name>/contract.yaml` 拷回 `<skill>/tests/contract.yaml` 即可。

## 验证集野生样本（放 `kit/validation/anomalies/`）

| 样本 | 来源 | 拉取 | 检测点 |
|---|---|---|---|
| W1-wild-dangling-scripts | trailofbits/skills@main `plugins/supply-chain-risk-auditor/skills/supply-chain-risk-auditor` | 整目录下载 | SKILL 引用的 scripts/collect.py 未发布 |
| W2-wild-dangling-references | nextlevelbuilder/ui-ux-pro-max-skill@main `.claude/skills/ui-ux-pro-max` | 整目录下载 | references/ 整目录缺失（另缺 reasoning_contract 模块） |

两者均需补一份最小 `tests/contract.yaml`（见 manifest.yaml 注释）。
拉取后 `python scripts/run_validation.py` 应保持 11/11。

## 许可

外部 skill 的权利归原作者（LambdaTest/Trail of Bits 为 MIT，anthropics 见其仓库 LICENSE）；
本仓库自有代码与文档可自由使用。

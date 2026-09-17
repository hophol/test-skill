# Skill 评测能力结构调研报告（结构篇 v3）

> 日期：2026-09-16 · 与 v2（逻辑篇）配套：v2 讲"怎么算"，本篇讲"由什么构成"。
> 材料来源：三方源码均为本地克隆/安装后直读（plugin-eval@openai/plugins、skill-up@alibaba 源码树、agentut@1.4.16 npm 包）；字段与类型均为**源码里的真实定义**，非文档转述。
> 覆盖：plugin-eval · agentut · skill-up（全结构）＋ skillgrade / comet / skill-eval-harness / 官方 evals.json（速览）＋ cc-eval（对照）。

---

## 1. plugin-eval（OpenAI evaluate-skill 本体）的结构

### 1.1 模块结构（src/，27 个文件）

~~~
src/
├─ cli.js                    命令分发（start/analyze/explain-budget/...）
├─ core/
│  ├─ schema.js              ★ 四个核心构造器（见 1.3）
│  ├─ analyze.js             analyze 主流程（target 解析→evaluators→scoring→render）
│  ├─ budget.js              三段预算计算（trigger/invoke/deferred）
│  ├─ baseline.js            阈值基线（常量矩阵 + 本机分位数）
│  ├─ scoring.js             penalty 矩阵 + 等级映射 + Fix First 排序
│  ├─ benchmark.js(26KB)     benchmark 工作流（init-benchmark/benchmark/usage-out）
│  ├─ benchmark-workspace.js 基准工作区管理
│  ├─ benchmark-events.js    事件流
│  ├─ observed-usage.js(12KB) 实测 usage 导入（Responses API 日志/Codex 会话导出/JSONL）
│  ├─ measurement-plan.js    度量计划生成
│  ├─ metric-packs.js        指标包（manifest 驱动）
│  ├─ improvement-brief.js   改进简报
│  ├─ presentation.js        At a Glance / Why It Matters / Fix First 文案层
│  ├─ compare.js             版本对比
│  └─ workflow-guide.js      聊天路由建议
├─ evaluators/               ★ 检查器家族（产 checks[]）
│  ├─ skill.js(10.7KB)       skill 结构/description 质量/断链/超尺寸
│  ├─ plugin.js(9.4KB)       .codex-plugin/plugin.json 清单
│  ├─ python.js(8.3KB)       圈复杂度/长行/缺测试
│  ├─ typescript.js(8.6KB)   TS 脚本质量
│  └─ coverage.js(5.5KB)     lcov/coverage.xml/Istanbul
├─ lib/                      frontmatter 解析 / files 遍历 / tokens 估算（10 行）
└─ renderers/                markdown(25.7KB)/html/json 渲染
~~~

### 1.2 顶层配置结构

无 YAML 配置——一切靠 **CLI 参数 + 目标路径**（这是它"零配置"的原因）；可选输入只有两样：
- metric-pack 的 manifest.json（fixtures/metric-pack/manifest.json 示例）
- observed-usage 的 JSONL（fixtures/observed-usage/responses.jsonl 示例）

### 1.3 运行时核心类型（core/schema.js，源码原文）

~~~
EvaluationResult = {
  schemaVersion: 1, tool: {name, version}, createdAt,
  target: {path, relativePath, kind},
  summary: {
    score, grade, riskLevel, riskReasons[],
    scoreBreakdown: {startingScore, totalDeductions, finalScore,
                     gradeThresholds: {A:93,B:85,C:70,D:55}},
    checkCounts: {total, pass, warn, fail, info, error, warning},
    deductions[], categoryDeductions[], topRecommendations[],
    whyBullets[], fixFirst[], watchNext[]
  },
  budgets: {method, invocation_policy,
            trigger_cost_tokens:  {value, band, thresholds{goodMax,moderateMax,heavyMax}, components[]},
            invoke_cost_tokens:   {同上},
            deferred_cost_tokens: {同上}},
  observedUsage: null | {...},
  checks: [Check], metrics: [Metric], artifacts: [Artifact],
  extensions: [], measurementPlan, improvementBrief, nextAction
}

Check  = {id, category, severity(error|warning|info), status(fail|warn|info|pass),
          message, evidence[], remediation[], source, targetPath?, why?}
Metric = {id, category, value, unit, band, source, targetPath?}
Artifact = {id, type, label, description, source, path?|data?}
budgets.components[] = {label, path, tokens, note}
~~~

### 1.4 产物结构

单文件报告（markdown/html/json 三选一）+ 可选 'measurement-plan' / 'init-benchmark' 生成的 '.plugin-eval/benchmark.json'。无目录型工作区（它不跑 agent）。

### 1.5 扩展点

- 加检查 = 在 evaluators/ 加一个文件并注册进 analyze.js；
- 加指标包 = manifest.json（metric-packs）；
- 阈值可被本机样本动态覆盖（baseline.js 的分位数路径）。

---

## 2. agentut 的结构

### 2.1 模块结构（src/，npm 包即此布局）

~~~
src/
├─ cli.ts                    命令入口（run/report/suggest/init/clean）
├─ commands/                 run.ts / report.ts / suggest.ts / init.ts / clean.ts
├─ parser/                   yaml.ts（用例解析）/ session.ts（opencode 会话导出解析）
├─ distiller/                opencode.ts（会话→测试用例蒸馏）/ extract.ts / factory.ts / types.ts
├─ executor/                 ★ verifier.ts(27KB 断言引擎) / fixture.ts（$WORKDIR 准备）
│                              / statistics.ts（runs/min_pass 聚合）
├─ runner/                   factory.ts / opencode.ts（spawn opencode run）
├─ process/                  manager.ts / tree-killer.ts（进程树击杀）
├─ suggest/                  generator/llm-generator.ts + prompt.ts（LLM 生成用例）
├─ output/                   json.ts / logger.ts / formatters/{jest,markdown,html}.ts
├─ types/index.ts(10.9KB)    ★ 全部类型（见 2.3）
plugins/opencode/agentut-plugins.ts   mock 注入插件（写入被测工作区）
~~~

### 2.2 用例（配置）结构——YAML 三层

~~~
YamlTestSuite
├─ name / description
├─ environments: { [名]: EnvironmentConfig }
│    EnvironmentConfig = { directory(必填), setup?: SetupAction[], agent? }
│    SetupAction = { copy: "src -> $WORKDIR/dst" } | { run: 命令 }
├─ scenarios: ScenarioConfig[]
│    ScenarioConfig = { name, environment, steps[], cleanup?(废弃),
│                        runs?, min_pass?, initial_session?, score?, run_args? }
│    StepConfig = { input, expected: Assertion[], timeout?, mock?: MockRule[], run_args? }
│    ScoreConfig = { judge?, prompt?, priority=10, min_score=0 }
│    MockRule = { tool, when?: Matcher[](AND), output?|error? }
└─ config: GlobalConfig
     GlobalConfig = { default_timeout?, parallel?, agent_cli?, runs=5?, min_pass=4?,
                      judges?: {[名]: AgentCliConfig} }
     AgentCliConfig = { runner: opencode|claude|gemini, command, model?, agent? }
~~~

### 2.3 运行时核心类型（types/index.ts，45 个导出类型里的关键 8 组）

~~~
Matcher = { equals? | contains? | containsOneOf? | regex? | oneOf? }   // 按优先级取第一个
ToolCallAssertion = { name: string|Matcher, input?: Record<string,Matcher>,
                      output?, status?: completed|error|pending, min_pass? }
FileContentAssertion = { file, text }
ExecCommandAssertion = { command, expect, timeout?, cwd? }
JudgedByAssertion   = { judge, prompt, timeout?, min_pass? }
Assertion = should_call_tool|should_not_call_tool|should_produce_file|
            file_content_contains|response_contains|exec_command|judged_by

OpenCodeRunOutput        一次 opencode run 的原始事件聚合
ExecutionContext         单次执行上下文（workDir/outputs/session）
TestSummary  = { total_scenarios, passed, failed, duration_ms, timestamp }
ScenarioResult = { runs, min_pass, passed_runs, runDetails[], tempDirectory }
AssertionStat = { type, value, passed_runs, total_runs, pass_rate(0-100), status }
RunStepDetail = { step_index, input, status, duration_ms, assertions[], actual_output }
StepResult / AssertionResult = { type, value, passed, message? }
SessionInfo/SessionSummary/FileDiff/Part/Message   ← distiller 的输入类型（会话结构）
~~~

### 2.4 产物结构

~~~
（默认 stdout/json；-o 指定时）
result JSON = { summary: TestSummary, scenarios: [ScenarioResult{ runDetails:[{
  steps:[RunStepDetail{assertions:[AssertionResult]}] }] }], total_score }
另有 markdown（PR 评论）/ html（分组表+Tab）/ jest（CI 退出码）四种格式；
临时工作区 .agentut/temp/<...>（默认保留，clean 命令清理）
~~~

### 2.5 扩展点

- 加断言 = types 里加 union 成员 + verifier.ts 加 verifyXxx；
- 换 runner = runner/factory.ts（claude/gemini 是占位）；
- mock = MockRule → 插件经 tool.execute.before/after 改参改果（原参存 metadata._agentutOriginalInput）。

---

## 3. skill-up 的结构

### 3.1 模块结构（Go，internal/ 19 个包 + pkg/ 2 个 + 分发 skill）

~~~
cmd/skill-up/        CLI main（最小化，委托 internal/cli）
internal/
├─ cli/              cobra 子命令：run/validate/list-cases/report/import/debug
├─ config/           schema.go(35 类型)/validator.go(31KB 全量校验)/loader/defaults/mcp_merge
├─ credential/       key 解析（flag→env→~/.skill-up/credentials.yaml）
├─ runtime/          工作区运行时：none / opensandbox
├─ agent/            引擎适配器：claude_code / codex / qoder_cli（+ SessionResumer）
├─ customengine/     自定义引擎（local|http 传输，session_result|text 响应）
├─ mcp/              MCP 供给（mock/real）
├─ skill/            把 skill 文件装进引擎约定路径（排除 evals/）
├─ evaluator/        ★ evaluator.go(54KB 编排)/multiturn.go(24KB)/fixtures.go/artifacts_collect.go
├─ judge/            ★ judge.go(接口)/expect.go/rule_based.go/script.go/agent_judge.go(32KB)
│                      /context_materializer.go/interpreter.go/factory.go
├─ evalevent/        事件模型 + JSONL sink（--event-log）
├─ report/           JSON/JUnit/HTML + Anthropic grading/benchmark
├─ runner/           端到端编排
└─ logging/ observability/ shellquote/ ui/ platform/ agentkind/ userconfig/
pkg/
├─ skillup/          可嵌入评测 API（semver 稳定）
└─ transcript/       转录解析助手
skills/skill-upper/  分发式 skill（引导 agent 走 skill-up 工作流，自带 evals/）
schemas/evalevent/   事件协议的版本化 JSON Schema
~~~

### 3.2 配置结构（internal/config/schema.go，35 个类型的完整清单）

~~~
EvalConfig = { schema_version:"v1alpha1", environment: Environment,
               mcp: MCPConfig, skills: []SkillRef, engine: EngineConfig,
               cases: CasesConfig, benchmark?: BenchmarkConfig, report?: ReportConfig }

Environment = { type: none|opensandbox, image?, workspace_mount="/workspace",
                env?: map, setup_steps?: []SetupStep{run},
                ready_timeout_seconds?, sandbox_timeout_seconds?, entrypoint?: []string,
                network_policy?: deny_all|allow_declared, allowed_egress?: []string,
                metadata?, kwargs?, use_server_proxy? }
MCPConfig   = { servers: []MCPServer{name, mode: mocked|real, transport: stdio|http,
                                     command?, args?, endpoint?, config_ref?} }
SkillRef    = { source: local_path|registry, path?, target?, include?, exclude? }
EngineConfig= { name: claude_code|codex|custom, version?, entry?(废弃),
                model: ModelConfig{provider, name, base_url?, params?},
                kwargs?: map, custom?: customengine.Config }
CasesConfig = { files: []string, defaults: CaseDefaults, parallelism?, retry_policy? }
CaseDefaults= { timeout_seconds?, max_turns?, collect_artifacts?: []glob(doublestar),
                expect?: Expect（切片字段追加、标量字段覆盖） }
RetryPolicy = { max_retries, retry_on: []timeout|error }
ReportConfig= { formats: []json|junit|html, artifacts?: []transcript }
BenchmarkConfig = { enabled }        // 两臂开关

CaseConfig = { id, title?, description?, tag?,
               input: Input{prompt | turns: []Turn},      // 互斥
               context?: Context, constraints?: Constraints,
               expect?: Expect, judge?: JudgeConfig, mcp?, collect_artifacts?, oracle? }
Turn        = { role(user), content, timeout_seconds?, post_condition?, capture?: []CaptureRule }
PostCondition = { must_contain_all?, must_contain_any?, must_not_contain?,
                  on_fail: fail(默认)|skip_remaining }
CaptureRule  = { variable, pattern(命名组)|jsonpath 二选一 }
Context     = { repo_fixture?, git: GitContext{init,checkout,apply_diff,remotes}, files: map }
Constraints = { timeout_seconds?, max_turns? }
Expect      = { must_contain?, must_not_contain?, exit_code?, files_exist?,
                files_not_exist?, file_contains?: [{path,content}]?, golden_file? }

JudgeConfig = { type: rule_based|script|agent_judge,
                success?: []Rule, failure?: []Rule,           // rule_based
                model?, skills?, criteria?: []string, pass_threshold=0.7,  // agent_judge
                timeout_seconds?, context?: JudgeContextConfig }
Rule = output_contains{all,any,not} | output_matches(Go regexp) | exit_code |
       tool_called{name,args} | turn_response_contains{turn,contains_all|any} |
       turn_response_not_contains | tool_called_in_turn{turn,name,args} |
       tool_not_called_in_turn | files_exist | files_not_exist
JudgeContextConfig = { profile: standard|minimal,
                       final_message|transcript|workspace_diff: include|truncate|file_ref|omit,
                       generated_files: index|include|omit, limits: {max_bytes=65536} }
~~~

### 3.3 运行时核心类型

~~~
judge.Judge 接口：Evaluate(ctx, Input) → (*Result, error)
judge.Input  = { CaseID, Transcript, FinalMessage, ExitCode, WorkspacePath,
                 SkillDir, WorkspaceDiff, GeneratedFiles, ArtifactDir,
                 SessionResult, TurnsExecuted, TurnsTotal }
judge.Result = { Status: PASS|FAIL|SKIP|ERROR, SkipReason?, ErrorReason?,
                 AssertionResults: [{Text, Passed, Evidence}], Summary }
judge.ExpectResult = { Passed, Failures[] }（短路闸产物）
evaluator.EvalResult = { CaseID, CaseName, Configuration: with_skill|without_skill,
                         Status, Prompt, FinalMessage, ExitCode, DurationMs,
                         TurnsExecuted, TurnsTotal, InputTokens, OutputTokens,
                         Grading *judge.Result, JudgeSession, ExpectResult, Error }
agent.SessionResult = { ExitCode, FinalMessage, Transcript, SessionID,
                        InputTokens, OutputTokens, Artifacts }（+ SessionResumer 接口）
~~~

### 3.4 产物结构

~~~
<skill-name>-workspace/
└─ iteration-N/
   ├─ benchmark.json / benchmark.md          聚合（run_summary.{with_skill,without_skill,delta}）
   ├─ result.json                            全量（含三态 requested/applied/observed_configuration）
   ├─ report.json / report.xml(JUnit)
   └─ <case-id>/
      ├─ eval_metadata.json                  {eval_id, eval_name, prompt, assertions}
      └─ with_skill/ | without_skill/ | old_skill/
         ├─ grading.json                     ★ Anthropic 兼容：expectations[{text,passed,evidence}]
         │                                     + summary{passed,failed,total,pass_rate}
         └─ outputs/
            ├─ workspace/**                  collect_artifacts 收集（成功/失败/超时都收）
            └─ agent/run/*.jsonl             引擎原始轨迹
~~~

### 3.5 扩展点

加引擎 = internal/agent 新适配器（实现 Agent + SessionResumer）；加 judge = 实现 Judge 接口经 factory 注册；加规则 = config.Rule 新成员 + rule_based 解释器；custom engine 走 customengine.Config（local/http + session_result/text）。

---

## 4. 其余能力结构速览（基于此前抓取的原文）

### 4.1 skillgrade（706★）

~~~
配置：单份 eval.yaml（顶层仅 version+skill）
defaults{agent,command,provider=docker,trials=5,timeout=300,threshold=0.8,
         grader_model,grader_provider,docker{base,setup},environment{cpus,memory_mb},acp}
tasks[]{name,instruction,workspace[]{src,dest,chmod},graders[],expected?,metadata?,solution?}
graders[]{type=deterministic|llm_rubric,run|rubric,provider?,model?,weight=1}
grader 输出契约：stdout 单 JSON {score:0..1, details:string, checks[]?:{name,passed,message}}；
                退出码 0=grader 跑成功（score 0 也算）；输入通道 env SKILLGRADE_INPUT={task,trial,expected,metadata}
组织：$import（文件/目录/glob/列表，成环报错）+ --filter=tier=easy,medium（同 key OR 跨 key AND）
~~~

### 4.2 comet（3024★，产品自评）

~~~
入口：comet eval <eval.yaml|SKILL.md> 或 --manifest/--skill-path 恰一
suite: local|langsmith|langfuse（local = pytest 任务文件）
产物：runs/comet-eval-<uuid>/summary.md|html + 回写仓库实验记录（quick|full）
CI：workflow_dispatch 手动 + regression_check.py --count 1 --tolerance 0.10 + 日志 always 上传
归因四分类：harness / workflow / task / model；排除留痕 sample_status/included/reason
~~~

### 4.3 skill-eval-harness（74★，方法论最严）

~~~
Manifest: evals/shared-benchmark.json（case 带 split/domain/difficulty/success_goals/trigger_type）
Variant: with_skill | without_skill | old_skill | ablation:ID；Model 为第三轴
Experimental pair = (case_id, model, run_number, population) 封闭值（缺臂 blocked/重臂 invalid）
断言四组：objective / script-oracle（stdout {score,max_score}）/ process（skill_invoked、
          command_order…，缺证据 fail-closed）/ efficiency / qualitative（judge/rubric）
Severity：critical（一票否决不入均值）| gate（搬通过率）| soft（只进 graded_score）
回归：指名断言翻转 + paired sign-flip ≥6 对 p≤0.05，不足 INDETERMINATE
~~~

### 4.4 官方 evals.json（Anthropic / agentskills 标准，最大公约数）

~~~
{ skill_name, evals: [{ id, prompt, expected_output, files?: [], assertions?: [] }] }
产物约定：<skill>-workspace/iteration-N/<eval>/{with_skill|without_skill|old_skill}/
          {outputs/, timing.json{total_tokens,duration_ms}, grading.json}
grading.json = { assertion_results|expectations: [{text,passed,evidence}],
                 summary: {passed,failed,total,pass_rate} }
benchmark.json = { run_summary: {with_skill, without_skill, delta:
                   {pass_rate|time_seconds|tokens: {mean, stddev}} } }
~~~

### 4.5 cc-eval（我们的，对照）

~~~
cases/<case>.json = { id, workspace(相对), artifacts[], artifact_patterns?[]glob,
                      fixture_allowlist?[], oracle:{file:content} | turn.oracle,
                      slots{:{answer}}, turns[{user, timeout_ms?, assert{...}, oracle?}],
                      assert?(案例级，如 must_call_skill_any_turn), arms?, repeats?,
                      canary?, dangerously_skip_permissions?, permission_mode?, timeout_ms? }
断言：must_call_skill[_any_turn] / must_not_call_skill / must_ask_user /
      must_not_ask / must_not_reask[] / forbid_tools[] / must_contain[] /
      must_write_file | must_write_file_pattern(glob) + must_contain_file[] /
      must_not_write_file_pattern
产物：out/runs/<case>.<arm>.run<k>/{report.json, grading.json(共享模块), turn-*.jsonl}
      + out/summary.json + out/benchmark.json（Anthropic 兼容，canary 剔除聚合）
~~~

---

## 5. 结构对比与结论

| 结构维度 | plugin-eval | agentut | skill-up | cc-eval |
|---|---|---|---|---|
| 配置形态 | 无配置（CLI 即参） | 单 YAML 三层 | eval.yaml+cases 双层、35 类型 | 单 JSON 用例 |
| 用例粒度 | 无用例（对象是 skill 本身） | scenario×step×assertion | case×turn×expect/judge | case×turn×assert(+案例级) |
| 判分单元 | Check（severity×status） | Assertion（布尔） | Judge(Input)→Result（接口） | 断言（布尔+glob） |
| 引擎抽象 | 无（不跑） | runner/factory（1 实现） | agent 适配器 + SessionResumer（3+custom） | runner 内联（claude） |
| 产物核心 | 单报告 JSON | 单结果 JSON（4 格式） | 目录树 + Anthropic 兼容 | 目录树 + Anthropic 兼容 |
| 最值得抄的结构 | Check/Metric/Artifact 三构造器 + components 可追溯 | Matcher 五档 + MockRule | Judge 接口 + Input 字段集 + Turn/PostCondition/Capture | —— |

**三个结构级洞察**：
1. **判分输入的"字段集"是分水岭**：agentut 只喂 outputs+workDir；skill-up 的 judge.Input 带 Transcript/WorkspaceDiff/GeneratedFiles/TurnsExecuted——后者的轮级断言（tool_called_in_turn）之所以可能，全靠 Input 里这些字段。我们 cc-eval 的"按轮断言"等价于把 Transcript 预切成了 turns[]，结构上已经对齐，缺的是把这层显式成接口。
2. **配置的表达力排序**：skill-up（35 类型，turn/post_condition/capture/expect/judge/context.git）> agentut（scenario/step/mock）> 官方 evals.json（最简）。官方格式是"交换格式"，不是"表达格式"——我们的用例 JSON 表达力已接近 agentut，缺 capture/git-context 两块。
3. **扩展点的三种哲学**：plugin-eval 加文件、agentut 加 union 成员、skill-up 加接口实现。接口式（skill-up）最贵但最干净，也是它能把三种 judge 塞进一个流程的原因。

## 6. 对我们的结构行动项

1. **断言层引入 plugin-eval 的三构造器**（Check{severity,status,penalty} / Metric / Artifact）——让我们报告里的每条断言带严重度与扣分，score 变得可解释；
2. **把判分抽成 judge(Input)→Result**（Input 字段集照抄 skill-up 的清单再 turns 化）；
3. **Matcher 五档并入 assert.mjs**；MockRule 结构留作 agent-mock 能力的 schema；
4. **用例 schema 补 capture 与 git context 两个结构**（skill-up 已验证其表达力）；
5. **components 级可追溯**：预算/产物断言都记 {label, path, value}，报告可点开到文件。

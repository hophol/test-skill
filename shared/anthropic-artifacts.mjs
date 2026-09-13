/**
 * Anthropic skill-creator compatible artifacts, shared by every engine adapter.
 *
 * Why one module: both engines must produce the *same* grading.json /
 * benchmark.json shapes, otherwise results are not comparable and cannot be fed
 * to ecosystem tooling (skill-up consumes exactly these shapes, and its
 * `--auto` mode reads Anthropic `evals.json` directly).
 *
 * Contract (do not rename these fields - skill-creator's viewer depends on
 * them):
 *   grading.json  -> { expectations: [{ text, passed, evidence }], summary: { passed, failed, total, pass_rate } }
 *   benchmark.json-> { run_summary: { with_skill|without_skill: { pass_rate|time_seconds|tokens: { mean } }, delta } }
 *
 * @module shared/anthropic-artifacts
 */

/**
 * Build an Anthropic-compatible grading.json from one run report.
 * Both engines normalize to: run.turns[].assertions[] = { id, passed, detail }.
 * @param run - a run report from either engine.
 * @returns grading object with expectations + summary.
 */
export function gradingFromRun(run) {
  const expectations = []
  for (const turn of run.turns || []) {
    for (const a of turn.assertions || []) {
      expectations.push({
        text: 'turn ' + turn.turn + ': ' + a.id,
        passed: !!a.passed,
        evidence: a.detail || '',
      })
    }
  }
  const passed = expectations.filter(e => e.passed).length
  return {
    expectations,
    summary: {
      passed,
      failed: expectations.length - passed,
      total: expectations.length,
      pass_rate: expectations.length === 0 ? 0 : Number((passed / expectations.length).toFixed(4)),
    },
  }
}

function armShape(stats) {
  if (!stats) return null
  return {
    pass_rate: { mean: stats.resolutionRate },
    time_seconds: { mean: Number(((stats.meanWallMs || 0) / 1000).toFixed(1)) },
    tokens: { mean: stats.meanTokens || 0 },
  }
}

function deltaOf(a, b) {
  if (!a || !b) return null
  return {
    pass_rate: Number((a.resolutionRate - b.resolutionRate).toFixed(3)),
    time_seconds: Number((((a.meanWallMs || 0) - (b.meanWallMs || 0)) / 1000).toFixed(1)),
    tokens: (a.meanTokens || 0) - (b.meanTokens || 0),
  }
}

/**
 * Build an Anthropic-compatible benchmark.json across cases and arms.
 * @param cases - [{ case, arms: { with_skill?, without_skill? }, lift? }]
 * @param meta - optional { engine, generatedAt }
 */
export function benchmarkFromCases(allCases, meta = {}) {
  // Canary cases carry an assertion that MUST fail, so including them would drag
  // every aggregate toward zero and make a healthy run look broken. They are
  // reported per-case but excluded from run_summary (same spirit as skilljack
  // excluding anti-trigger tasks from the invocation rate).
  const canary = allCases.filter(c => c.canary !== undefined)
  const cases = allCases.filter(c => c.canary === undefined)
  const sum = (arms, key) => arms.map(c => c.arms?.[key]).filter(Boolean)
  const allWith = sum(cases, 'with_skill')
  const allWithout = sum(cases, 'without_skill')
  const combined = (list, field) => (list.length === 0 ? null : {
    pass_rate: { mean: Number((list.reduce((a, s) => a + s.resolutionRate, 0) / list.length).toFixed(3)) },
    time_seconds: { mean: Number((list.reduce((a, s) => a + (s.meanWallMs || 0), 0) / list.length / 1000).toFixed(1)) },
    tokens: { mean: Math.round(list.reduce((a, s) => a + (s.meanTokens || 0), 0) / list.length) },
  })
  const withShape = combined(allWith, 'with_skill')
  const withoutShape = combined(allWithout, 'without_skill')
  return {
    metadata: {
      engine: meta.engine || 'unknown',
      generated_at: meta.generatedAt || new Date().toISOString(),
      cases: cases.length,
      canary_cases_excluded: canary.length,
      runs_per_configuration: Math.max(0, ...cases.flatMap(c => Object.values(c.arms || {}).map(s => s.runs || 0))),
    },
    run_summary: {
      with_skill: withShape,
      without_skill: withoutShape,
      delta: withShape && withoutShape ? {
        pass_rate: Number((withShape.pass_rate.mean - withoutShape.pass_rate.mean).toFixed(3)),
        time_seconds: Number((withShape.time_seconds.mean - withoutShape.time_seconds.mean).toFixed(1)),
        tokens: withShape.tokens.mean - withoutShape.tokens.mean,
      } : null,
    },
    cases: allCases.map(c => ({
      case: c.case,
      lift: c.lift,
      canary: c.canary,
      with_skill: armShape(c.arms?.with_skill),
      without_skill: armShape(c.arms?.without_skill),
    })),
  }
}

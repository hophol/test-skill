/**
 * cc-eval statistics. The Anthropic-compatible artifacts now live in
 * shared/anthropic-artifacts.mjs so both engine adapters emit identical shapes.
 *
 * @module cc-eval/stats
 */
export { gradingFromRun as gradingJson, benchmarkFromCases } from '../../shared/anthropic-artifacts.mjs'

/** Wald 95% interval - same formula skilljack uses (collapses at p=0/1). */
export function wald(p, n) {
  if (n <= 0) return [0, 1]
  const half = 1.96 * Math.sqrt((p * (1 - p)) / n)
  return [Math.max(0, p - half), Math.min(1, p + half)]
}

/** Wilson score interval - stays honest when every run passes or fails. */
export function wilson(p, n) {
  if (n <= 0) return [0, 1]
  const z = 1.96
  const denom = 1 + (z * z) / n
  const centre = (p + (z * z) / (2 * n)) / denom
  const spread = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom
  return [Math.max(0, centre - spread), Math.min(1, centre + spread)]
}

/** Per-arm aggregate over N runs of one case. */
export function armStats(runs) {
  const n = runs.length
  const passed = runs.filter(r => r.passed).length
  const p = n === 0 ? 0 : passed / n
  const mean = key => (n === 0 ? 0 : runs.reduce((a, r) => a + (key(r) || 0), 0) / n)
  return {
    runs: n,
    passed,
    resolutionRate: Number(p.toFixed(3)),
    passAtK: runs.some(r => r.passed),
    ci95Wald: wald(p, n).map(v => Number(v.toFixed(3))),
    ci95Wilson: wilson(p, n).map(v => Number(v.toFixed(3))),
    meanTurns: Number(mean(r => r.turnsUsed).toFixed(2)),
    meanWallMs: Math.round(mean(r => r.wallMs)),
    meanCostUsd: Number(mean(r => r.costUsd).toFixed(4)),
    meanTokens: Math.round(mean(r => (r.tokens ? r.tokens.input + r.tokens.output : (r.usage ? r.usage.input + r.usage.output : 0)))),
    skillInvocations: runs.filter(r => r.skillCalls > 0).length,
  }
}

#!/usr/bin/env node
/**
 * Aggregate every out/<case>.<arm>.run<k>.json into out/summary.json.
 *
 * Metrics follow the skilljack/SkillsBench shapes:
 *   resolutionRate = passed runs / runs
 *   pass@k         = at least one run passed
 *   ci95           = p +/- 1.96*sqrt(p(1-p)/n)   (Wald, clamped to [0,1])
 *   lift           = resolutionRate(with) - resolutionRate(without)
 *   macroLift      = mean of per-case lifts
 * A canary case carries an assertion that must always fail; if any canary run
 * passes, the whole summary is marked untrustworthy.
 *
 * Usage: node report.mjs
 */
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { benchmarkFromCases, gradingFromRun } from '../shared/anthropic-artifacts.mjs'

const HERE = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
const outDir = join(HERE, 'out')

const runs = []
for (const file of readdirSync(outDir).filter(f => f.endsWith('.json') && f !== 'summary.json')) {
  const [caseId, arm, runTag] = file.replace(/\.json$/, '').split('.')
  if (!caseId || !arm) continue
  const report = JSON.parse(readFileSync(join(outDir, file), 'utf8'))
  // Anthropic-compatible grading.json next to the run report (same layout as cc-eval).
  const gradingDir = join(outDir, 'grading')
  mkdirSync(gradingDir, { recursive: true })
  writeFileSync(join(gradingDir, file.replace(/\.json$/, '.grading.json')), JSON.stringify(gradingFromRun(report), null, 2), 'utf8')
  runs.push({
    case: caseId, arm, run: runTag || 'run1', file,
    passed: !!report.passed,
    turnsUsed: report.turnsUsed || 0,
    failedAssertions: (report.failedAssertions || []).map(a => a.id),
    tokens: report.totals || { inputTokens: 0, outputTokens: 0 },
    wallMs: report.wallMs || 0,
    skillCalls: (report.turns || []).flatMap(t => t.tools).filter(n => n === 'skill').length,
  })
}

function stats(list) {
  const n = list.length
  const passed = list.filter(r => r.passed).length
  const p = n === 0 ? 0 : passed / n
  const z = 1.96
  const half = n === 0 ? 1 : z * Math.sqrt((p * (1 - p)) / n)
  // Wilson score interval: unlike Wald it does not collapse to [1,1] when every
  // run passes (or [0,0] when every run fails), so it stays honest at n=3.
  const denom = 1 + (z * z) / (n || 1)
  const centre = (p + (z * z) / (2 * (n || 1))) / denom
  const spread = n === 0 ? 1 : (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom
  const mean = key => n === 0 ? 0 : Math.round(list.reduce((a, r) => a + key(r), 0) / n)
  return {
    runs: n,
    passed,
    resolutionRate: Number(p.toFixed(3)),
    passAtK: list.some(r => r.passed),
    ci95: [Number(Math.max(0, p - half).toFixed(3)), Number(Math.min(1, p + half).toFixed(3))],
    ci95Wilson: [Number(Math.max(0, centre - spread).toFixed(3)), Number(Math.min(1, centre + spread).toFixed(3))],
    meanTurns: Number((n === 0 ? 0 : list.reduce((a, r) => a + r.turnsUsed, 0) / n).toFixed(2)),
    meanWallMs: mean(r => r.wallMs),
    meanTokens: mean(r => r.tokens.inputTokens + r.tokens.outputTokens),
    skillInvocations: list.filter(r => r.skillCalls > 0).length,
  }
}

const cases = [...new Set(runs.map(r => r.case))].sort()
const table = []
let totalTokens = 0
for (const caseId of cases) {
  const arms = {}
  for (const arm of [...new Set(runs.filter(r => r.case === caseId).map(r => r.arm))]) {
    const list = runs.filter(r => r.case === caseId && r.arm === arm)
    arms[arm] = stats(list)
    totalTokens += list.reduce((a, r) => a + r.tokens.inputTokens + r.tokens.outputTokens, 0)
  }
  const w = arms.with_skill, b = arms.without_skill
  const isCanary = caseId.startsWith('canary-')
  table.push({
    case: caseId,
    arms,
    lift: w && b ? Number((w.resolutionRate - b.resolutionRate).toFixed(3)) : undefined,
    canary: isCanary ? !Object.values(arms).some(a => a.passed > 0) : undefined,
  })
}
const lifts = table.filter(t => t.lift !== undefined).map(t => t.lift)
const macroLift = lifts.length ? Number((lifts.reduce((a, v) => a + v, 0) / lifts.length).toFixed(3)) : undefined
const canaryBroken = table.some(t => t.canary === false)
const summary = {
  generatedAt: new Date().toISOString(),
  cases: table,
  macroLift,
  totalTokens,
  canary: table.some(t => t.canary !== undefined) ? (canaryBroken ? 'BROKEN' : 'ok') : 'absent',
}
writeFileSync(join(outDir, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8')
writeFileSync(join(outDir, 'benchmark.json'), JSON.stringify(benchmarkFromCases(table, { engine: 'dsh', generatedAt: summary.generatedAt }), null, 2), 'utf8')

process.stdout.write('=== skill-eval report ===\n')
for (const t of table) {
  process.stdout.write(t.case + '\n')
  for (const [arm, s] of Object.entries(t.arms)) {
    process.stdout.write('  ' + arm.padEnd(14) + s.passed + '/' + s.runs + ' passed  rate=' + s.resolutionRate +
      ' ci95=' + s.ci95.join(',') + ' wilson=' + s.ci95Wilson.join(',') + '  pass@k=' + s.passAtK +
      '  turns=' + s.meanTurns + '  wall=' + (s.meanWallMs / 1000).toFixed(1) + 's  tokens=' + s.meanTokens + '\n')
  }
  if (t.lift !== undefined) process.stdout.write('  lift=' + t.lift + '\n')
  if (t.canary !== undefined) process.stdout.write('  canary=' + (t.canary ? 'ok (failed as required)' : 'BROKEN') + '\n')
}
process.stdout.write('macro lift: ' + macroLift + '\ncanary: ' + summary.canary + '\ntotal tokens: ' + totalTokens + '\n')
process.stdout.write('summary -> ' + join(outDir, 'summary.json') + '\n')

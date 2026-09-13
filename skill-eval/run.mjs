#!/usr/bin/env node
/**
 * skill-eval batch runner.
 *
 * Runs every case R times per arm:
 *   with_skill    - the fixture workspace keeps .dsh/skills/**
 *   without_skill - the same workspace with .dsh/skills removed
 * Writing one report per run: out/<case>.<arm>.run<k>.json
 * Aggregate with report.mjs (resolution rate, pass@k, 95% CI, lift).
 *
 * Usage: node run.mjs [caseId ...] [--arms a,b] [--repeats N]
 */
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'

const HERE = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
const argv = process.argv.slice(2)
function flag(name, dflt) {
  const i = argv.indexOf('--' + name)
  return i === -1 ? dflt : argv[i + 1]
}
// A bare token is a case id unless it is the value of a preceding --flag.
const only = argv.filter((a, i) => !a.startsWith('--') && !(i > 0 && argv[i - 1].startsWith('--')))
const arms = flag('arms', 'with_skill,without_skill').split(',')
const repeats = Number(flag('repeats', process.env.DSH_EVAL_REPEATS || '1'))
const DSH_BIN = flag('dsh', process.env.DSH_BIN || 'D:\\Users\\Administrator\\AppData\\Local\\nvm\\v24.19.0\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js')
const DSH_NODE = flag('node', process.env.DSH_NODE || 'D:\\Users\\Administrator\\AppData\\Local\\nvm\\v24.19.0\\node.exe')

const casesDir = join(HERE, 'cases')
const caseIds = only.length > 0 ? only : readFileSync(join(casesDir, 'INDEX.txt'), 'utf8').trim().split(/\r?\n/).filter(Boolean)
const workRoot = join(HERE, 'out', 'ws')
rmSync(workRoot, { recursive: true, force: true })

const started = Date.now()
process.stdout.write('cases=' + caseIds.join(',') + ' arms=' + arms.join(',') + ' repeats=' + repeats + '\n')
for (const caseId of caseIds) {
  const casePath = join(casesDir, caseId + '.json')
  const testCase = JSON.parse(readFileSync(casePath, 'utf8'))
  // Relative case workspaces resolve against the skill-eval project root.
const fixture = resolve(HERE, testCase.workspace)
  // Fixture hygiene: a previous run's artifact must never satisfy this run's
  // assertions (that silently turns every arm into a false PASS).
  for (const artifact of testCase.artifacts || []) {
    if (existsSync(join(fixture, artifact))) {
      throw new Error('dirty fixture: ' + caseId + ' still contains ' + artifact + ' - delete it before running')
    }
  }
  for (const arm of (testCase.arms || arms)) {
    for (let k = 1; k <= repeats; k++) {
      const ws = join(workRoot, caseId, arm, 'run-' + k, 'workspace')
      mkdirSync(dirname(ws), { recursive: true })
      cpSync(fixture, ws, { recursive: true })
      if (arm === 'without_skill') rmSync(join(ws, '.dsh'), { recursive: true, force: true })
      const outPath = join(HERE, 'out', caseId + '.' + arm + '.run' + k + '.json')
      const child = spawnSync(DSH_NODE, [DSH_BIN, '--profile', 'skilleval', '--patch', join(HERE, 'overlay.yml')], {
        cwd: HERE,
        stdio: 'inherit',
        env: {
          ...process.env,
          DSH_EVAL_CASE: casePath,
          DSH_EVAL_WORKSPACE: ws,
          DSH_EVAL_OUT: outPath,
          DSH_EVAL_UQ: testCase.user_questions || 'scripted',
        },
      })
      const report = existsSync(outPath) ? JSON.parse(readFileSync(outPath, 'utf8')) : undefined
      process.stdout.write('[run] ' + caseId + ' / ' + arm + ' #' + k + ' -> ' +
        (report ? (report.passed ? 'PASS' : 'FAIL(' + report.failedAssertions.map(a => a.id).join(',') + ')') : 'NO-REPORT') +
        ' exit=' + child.status + ' turns=' + (report ? report.turnsUsed : '-') + '\n')
    }
  }
}
process.stdout.write('batched in ' + Math.round((Date.now() - started) / 1000) + 's; now run: node report.mjs\n')

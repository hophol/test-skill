#!/usr/bin/env node
/**
 * Grader self-test (oracle gate, lite).
 *
 * For every case it writes the case's declared expected artifacts into a temp
 * workspace and runs the same assertion code the runner uses. Two properties
 * must hold, and neither costs a token:
 *   positive control - the declared artifact satisfies every file assertion
 *   negative control - the canary's impossible assertion still fails
 * A case that cannot pass this gate is rejected before any model runs (the
 * standard "oracle must pass before the agent runs" rule).
 *
 * Usage: node oracle.mjs
 */
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { checkFileAssertions } from './plugin/assertions.mjs'

const HERE = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
const casesDir = join(HERE, 'cases')
const ids = readFileSync(join(casesDir, 'INDEX.txt'), 'utf8').trim().split(/\r?\n/).filter(Boolean)

let failed = 0
for (const id of ids) {
  const testCase = JSON.parse(readFileSync(join(casesDir, id + '.json'), 'utf8'))
  const ws = mkdtempSync(join(tmpdir(), 'skill-eval-oracle-'))
  const problems = []
  try {
    // positive control: materialise the declared expected artifact
    for (const [file, content] of Object.entries(testCase.oracle || {})) {
      mkdirSync(dirname(join(ws, file)), { recursive: true })
      writeFileSync(join(ws, file), content, 'utf8')
    }
    if (testCase.canary !== true) {
      for (const turn of testCase.turns || []) {
        const spec = turn.assert || {}
        if (!spec.must_write_file) continue
        const result = checkFileAssertions(ws, spec)
        if (!result.passed) problems.push('positive control failed: ' + result.id + ' -> ' + result.detail)
      }
    }
    if (testCase.canary === true) {
      // negative control: the canary must fail even with the positive artifacts present
      const anyPassed = (testCase.turns || []).some(t => {
        const r = checkFileAssertions(ws, t.assert || {})
        return r && r.passed
      })
      if (anyPassed) problems.push('negative control failed: canary assertion passed')
    }
  } finally {
    rmSync(ws, { recursive: true, force: true })
  }
  if (problems.length === 0) process.stdout.write(id.padEnd(22) + 'gate: OK\n')
  else { failed++; process.stdout.write(id.padEnd(22) + 'gate: FAIL\n    ' + problems.join('\n    ') + '\n') }
}
process.stdout.write(failed === 0 ? '\noracle gate: all cases solvable by construction\n' : '\noracle gate: ' + failed + ' case(s) rejected\n')
process.exitCode = failed === 0 ? 0 : 1

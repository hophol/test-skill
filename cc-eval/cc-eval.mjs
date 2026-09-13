#!/usr/bin/env node
/**
 * cc-eval - evaluate Agent Skill execution inside Claude Code.
 *
 * It does not grade the SKILL.md text: it runs the same scripted conversation
 * twice - once with the skill installed in the workspace, once without - and
 * asserts on the *process* (which tools ran, in which turn, in which order) and
 * on the *result* (what the world looks like afterwards).
 *
 *   cc-eval oracle                 # grader self-test, 0 tokens
 *   cc-eval run [caseId] [--repeats N] [--arms a,b]
 *   cc-eval report                 # aggregate every run into summary/benchmark
 *
 * Claude Code is driven with: claude -p <turn> --output-format stream-json
 * --verbose [--resume <session-id>]   (one process per turn, one session total)
 */
import { spawn, spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, openSync, closeSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { checkCaseAssertions, checkTurnAssertions, findFilesByPattern } from './lib/assert.mjs'
import { armStats, benchmarkFromCases, gradingJson } from './lib/stats.mjs'

const HERE = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
const CASES = join(HERE, 'cases')
const OUT = join(HERE, 'out')

function parseArgs(argv) {
  const flags = {}
  const rest = []
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith('--')) flags[a.slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true
    else rest.push(a)
  }
  return { flags, rest }
}

function readJson(p) { return JSON.parse(readFileSync(p, 'utf8')) }
function listCases() {
  const index = join(CASES, 'INDEX.txt')
  if (existsSync(index)) return readFileSync(index, 'utf8').trim().split(/\r?\n/).filter(Boolean)
  return readdirSync(CASES).filter(f => f.endsWith('.json')).map(f => f.replace(/\.json$/, ''))
}

/** Fresh workspace for one (case, arm, run): copy fixture, then drop the skill for the baseline arm. */
function prepareWorkspace(testCase, arm, runIndex) {
  // Case workspaces may be relative (recommended, keeps the repo portable);
  // they resolve against the cc-eval project root, not the caller's cwd.
  const fixture = resolve(HERE, testCase.workspace)
  for (const artifact of testCase.artifacts || []) {
    if (existsSync(join(fixture, artifact))) {
      throw new Error('dirty fixture: ' + testCase.id + ' still contains ' + artifact + ' - delete it first')
    }
  }
  // Fixture allowlist: some cases REQUIRE an otherwise-empty workspace (e.g. a
  // "no requirements yet" boundary turn). A leftover input file there silently
  // changes what the case measures - this guard turns that into a loud error.
  if (testCase.fixture_allowlist) {
    const allowed = testCase.fixture_allowlist
    const strays = findFilesByPattern(fixture, '**/*').filter(p => {
      const rel = p.slice(fixture.length + 1).replace(/\\/g, '/')
      return !allowed.some(prefix => rel === prefix || rel.startsWith(prefix + '/') || prefix === '*')
    })
    if (strays.length > 0) {
      throw new Error('fixture not empty enough for ' + testCase.id + ': ' + strays.slice(0, 3).join(', ') + ' (allowed: ' + allowed.join(',') + ')')
    }
  }
  // Same hygiene for variable-name outputs (fe-req-{feature}.md style).
  for (const pattern of testCase.artifact_patterns || []) {
    const hits = findFilesByPattern(fixture, pattern)
    if (hits.length > 0) {
      throw new Error('dirty fixture: ' + testCase.id + ' already matches artifact pattern ' + pattern + ' -> ' + hits[0])
    }
  }
  const ws = join(OUT, 'ws', testCase.id, arm, 'run-' + runIndex, 'workspace')
  // A rerun must be hermetic: cpSync overlays, it does not delete, so files a
  // previous run left behind would survive and satisfy (or trip) this run's
  // assertions. Wipe the destination first.
  rmSync(ws, { recursive: true, force: true })
  mkdirSync(dirname(ws), { recursive: true })
  cpSync(fixture, ws, { recursive: true })
  if (arm === 'without_skill') {
    for (const dir of ['.claude', '.agents', '.dsh']) rmSync(join(ws, dir), { recursive: true, force: true })
  }
  return ws
}

/**
 * Kill a runaway CLI process and its children. On Windows child.kill() only
 * terminates the direct child, so use taskkill /T; agents spawn helpers.
 */
function killTree(pid) {
  if (pid === undefined) return
  if (process.platform === 'win32') {
    try { spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' }) } catch { /* already gone */ }
  } else {
    try { process.kill(pid, 'SIGKILL') } catch { /* already gone */ }
  }
}

/**
 * Run one conversation turn in its own process. stdout/stderr go straight to
 * files (no pipes), which keeps large streams intact and works in sandboxes
 * that forbid piped stdio. Async so several runs can proceed in parallel;
 * turns inside one run are still awaited one by one (they share a session).
 */
function runTurn(opts) {
  const args = ['-p', opts.prompt, '--output-format', 'stream-json', '--verbose']
  if (opts.sessionId) args.push('--resume', opts.sessionId)
  if (opts.model) args.push('--model', opts.model)
  if (opts.dangerouslySkipPermissions) args.push('--dangerously-skip-permissions')
  else args.push('--permission-mode', opts.permissionMode || 'acceptEdits')
  mkdirSync(opts.runDir, { recursive: true })
  const outPath = join(opts.runDir, 'turn-' + opts.turn + '.jsonl')
  const errPath = join(opts.runDir, 'turn-' + opts.turn + '.err')
  const outFd = openSync(outPath, 'w')
  const errFd = openSync(errPath, 'w')
  const started = Date.now()
  return new Promise(resolve => {
    let settled = false
    let timedOut = false
    const child = spawn(opts.claudeBin || 'claude', args, {
      cwd: opts.workspace, stdio: ['ignore', outFd, errFd], windowsHide: true,
    })
    const timer = setTimeout(() => { timedOut = true; killTree(child.pid) }, opts.timeoutMs)
    const finish = status => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      closeSync(outFd); closeSync(errFd)
      resolve({ outPath, errPath, status, timedOut, wallMs: Date.now() - started })
    }
    child.on('error', () => finish(null))
    child.on('close', code => finish(code))
  })
}

/** Normalize the stream-json NDJSON into the view assertions consume. */
function normalizeTurn(file, turn) {
  const lines = existsSync(file) ? readFileSync(file, 'utf8').split(/\r?\n/).filter(l => l.trim().startsWith('{')) : []
  const toolCalls = []
  let assistantText = ''
  let sessionId
  let result = null
  let init = null
  for (const line of lines) {
    let e; try { e = JSON.parse(line) } catch { continue }
    if (e.type === 'system' && e.subtype === 'init') init = e
    if (e.session_id && !sessionId) sessionId = e.session_id
    if (e.type === 'assistant' && e.message && Array.isArray(e.message.content)) {
      for (const b of e.message.content) {
        if (b.type === 'tool_use') toolCalls.push({ name: b.name, input: JSON.stringify(b.input || {}).slice(0, 400) })
        if (b.type === 'text' && b.text) assistantText = b.text
      }
    }
    if (e.type === 'user' && e.message && Array.isArray(e.message.content)) {
      for (const b of e.message.content) {
        if (b.type === 'tool_result') {
          const text = typeof b.content === 'string' ? b.content : JSON.stringify(b.content)
          toolCalls.push({ name: '<<tool_result>>', input: String(text).slice(0, 200) })
        }
      }
    }
    if (e.type === 'result') result = e
  }
  return {
    turn,
    sessionId: sessionId || (init && init.session_id),
    tools: (init && init.tools) || [],
    toolCalls,
    assistantText,
    numTurns: result ? result.num_turns : undefined,
    durationMs: result ? result.duration_ms : undefined,
    costUsd: result ? result.total_cost_usd : undefined,
    usage: result && result.usage ? {
      input: result.usage.input_tokens || 0,
      output: result.usage.output_tokens || 0,
      cacheRead: result.usage.cache_read_input_tokens || 0,
    } : undefined,
    observedModels: result && result.modelUsage ? Object.keys(result.modelUsage) : [],
    permissionDenials: result ? result.permission_denials : undefined,
    isError: result ? !!result.is_error : true,
    subtype: result ? result.subtype : undefined,
    finalText: result ? String(result.result || '') : '',
  }
}

async function cmdRun(flags, rest) {
  const repeats = Number(flags.repeats || 1)
  // Concurrency is at the run level (case x arm x repeat). Turns inside one run
  // stay sequential because they share one --resume session. Every run already
  // owns its workspace copy, so parallel runs cannot touch each other's files.
  const concurrency = Math.max(1, Number(flags.concurrency || 1))
  const arms = String(flags.arms || 'with_skill,without_skill').split(',')
  const caseIds = rest.length > 0 ? rest : listCases()
  const jobs = []
  for (const caseId of caseIds) {
    const testCase = readJson(join(CASES, caseId + '.json'))
    const caseArms = testCase.arms || arms
    for (const arm of caseArms) {
      for (let k = 1; k <= (testCase.repeats || repeats); k++) {
        const ws = prepareWorkspace(testCase, arm, k)
        const runDir = join(OUT, 'runs', caseId + '.' + arm + '.run' + k)
        rmSync(runDir, { recursive: true, force: true })
        mkdirSync(runDir, { recursive: true })
        jobs.push({ caseId, testCase, arm, k, ws, runDir })
      }
    }
  }
  process.stdout.write('[cc-eval] runs=' + jobs.length + ' concurrency=' + concurrency + '\n')
  const results = []
  let cursor = 0
  const workers = Array.from({ length: Math.min(concurrency, jobs.length) }, () => (async () => {
    while (cursor < jobs.length) {
      const job = jobs[cursor++]
      results.push(await executeRun(job, flags))
    }
  })())
  await Promise.all(workers)
  return verdictOf(results)
}

/** One (case, arm, repeat) run: the turns are awaited one by one (one session). */
async function executeRun(job, flags) {
  const { caseId, testCase, arm, k, ws, runDir } = job
  {
    const turnSpecs = testCase.turns || [{ user: testCase.prompt }]
    let sessionId
        const turns = []
        let wallMs = 0
        let aborted = false
        for (let i = 0; i < turnSpecs.length; i++) {
          let prompt = turnSpecs[i].user
          for (const [slot, val] of Object.entries(testCase.slots || {})) {
            prompt = prompt.split('{{' + slot + '}}').join(val.answer)
          }
          const r = await runTurn({
            prompt, sessionId, workspace: ws, runDir, turn: i + 1,
            timeoutMs: turnSpecs[i].timeout_ms || testCase.timeout_ms || 240000,
            model: flags.model || testCase.model,
            dangerouslySkipPermissions: testCase.dangerously_skip_permissions === true,
            permissionMode: testCase.permission_mode,
          })
          wallMs += r.wallMs
          if (!sessionId && existsSync(r.outPath)) {
            const sniff = normalizeTurn(r.outPath, i + 1)
            sessionId = sniff.sessionId
          }
          const turn = normalizeTurn(r.outPath, i + 1)
          turn.timedOut = r.timedOut
          turn.exitCode = r.status
          turn.prompt = prompt
          turn.assertions = checkTurnAssertions(turn, turnSpecs[i].assert || {}, ws)
          turns.push(turn)
          process.stdout.write('[cc-eval] ' + caseId + '/' + arm + '#' + k + ' turn ' + (i + 1) +
            ' tools=[' + turn.toolCalls.map(c => c.name).filter(n => n !== '<<tool_result>>').join(',') + '] ' +
            'assert=' + (turn.assertions.every(a => a.passed) ? 'PASS' : 'FAIL(' + turn.assertions.filter(a => !a.passed).map(a => a.id).join(',') + ')') + '\n')
          if (r.timedOut || turn.isError || (turnSpecs[i].assert && turnSpecs[i].assert.must_stop_on_fail !== false && turn.assertions.some(a => !a.passed) && testCase.stop_on_failed_turn)) {
            aborted = true
            break
          }
        }
        const caseAssertions = checkCaseAssertions(turns, testCase.assert || {}, ws)
        const failed = turns.flatMap(t => t.assertions).concat(caseAssertions).filter(a => !a.passed)
        const report = {
          caseAssertions,
          case: caseId, arm, run: k, workspace: ws,
          sessionId,
          requestedModel: flags.model || testCase.model || '(cli default)',
          observedModels: [...new Set(turns.flatMap(t => t.observedModels || []))],
          turnsUsed: turns.length, wallMs, aborted,
          costUsd: Number(turns.reduce((a, t) => a + (t.costUsd || 0), 0).toFixed(6)),
          tokens: turns.reduce((a, t) => ({ input: a.input + (t.usage ? t.usage.input : 0), output: a.output + (t.usage ? t.usage.output : 0), cacheRead: a.cacheRead + (t.usage ? t.usage.cacheRead : 0) }), { input: 0, output: 0, cacheRead: 0 }),
          skillCalls: turns.filter(t => t.toolCalls.some(c => c.name === 'Skill' || c.name === 'skill')).length,
          passed: failed.length === 0,
          failedAssertions: failed.map(a => ({ turn: a.id, detail: a.detail })),
          turns,
        }
        writeFileSync(join(runDir, 'report.json'), JSON.stringify(report, null, 2), 'utf8')
        writeFileSync(join(runDir, 'grading.json'), JSON.stringify(gradingJson(report), null, 2), 'utf8')
        writeFileSync(join(OUT, caseId + '.' + arm + '.run' + k + '.json'), JSON.stringify(report, null, 2), 'utf8')
  process.stdout.write('[cc-eval] -> ' + caseId + '/' + arm + '#' + k + ' ' + (report.passed ? 'PASS' : 'FAIL') + ' turns=' + report.turnsUsed + ' wall=' + (wallMs / 1000).toFixed(1) + 's cost=$' + report.costUsd + '\n')
  return report
  }
}

/**
 * Exit code answers one question only: "did the skill arm behave as required?"
 * A failing baseline is the *expected* outcome (that is the lift), and a canary
 * that fails is the *expected* outcome too - it only breaks when it passes.
 */
function verdictOf(results) {
  const byCase = new Map()
  for (const r of results) {
    const entry = byCase.get(r.case) || { failedSkillArm: false, canaryPassed: false, infra: false }
    if (r.case.startsWith('canary-')) { if (r.passed) entry.canaryPassed = true } else if (r.arm === 'with_skill' && !r.passed) entry.failedSkillArm = true
    if (r.aborted) entry.infra = true
    byCase.set(r.case, entry)
  }
  for (const [caseId, e] of byCase) {
    if (e.failedSkillArm || e.canaryPassed || e.infra) {
      process.stdout.write('[cc-eval] verdict: ' + caseId + ' -> ' + (e.canaryPassed ? 'CANARY BROKEN' : e.failedSkillArm ? 'SKILL ARM FAILED' : 'RUN ABORTED') + '\n')
      return 1
    }
  }
  return 0
}

function cmdOracle() {
  let failed = 0
  for (const caseId of listCases()) {
    const testCase = readJson(join(CASES, caseId + '.json'))
    const ws = join(OUT, 'oracle', caseId)
    rmSync(ws, { recursive: true, force: true })
    mkdirSync(ws, { recursive: true })
    const problems = []
    // Artifacts materialize cumulatively per turn: a turn's assertions see the
    // state the world should be in AT THAT TURN. Case-level oracle (legacy /
    // single-turn cases) is the final state, applied before the last turn.
    const turns = testCase.turns || []
    const materialize = entries => {
      for (const [file, content] of Object.entries(entries || {})) {
        mkdirSync(dirname(join(ws, file)), { recursive: true })
        writeFileSync(join(ws, file), content, 'utf8')
      }
    }
    // The oracle evaluates ONLY artifact assertions (exact or glob) through the
    // same code path the live runner uses; a synthetic turn has no tool calls, so
    // process assertions would fail by construction and are filtered out.
    const fileOnly = t => checkTurnAssertions({ toolCalls: [], assistantText: '' }, t.assert || {}, ws)
      .filter(a => a.id === 'must_write_file' || a.id === 'must_write_file_pattern' || a.id === 'must_not_write_file_pattern')
    if (testCase.canary !== true) {
      turns.forEach((t, i) => {
        materialize(t.oracle)
        if (i === turns.length - 1) materialize(testCase.oracle)
        for (const r of fileOnly(t)) {
          if (!r.passed) problems.push('positive control failed (turn ' + (i + 1) + '): ' + r.id + ' -> ' + r.detail)
        }
      })
    } else {
      materialize(testCase.oracle)
      const anyPassed = turns.some(t => fileOnly(t).some(r => r.passed && r.id !== 'must_not_write_file_pattern'))
      if (anyPassed) problems.push('negative control failed: canary assertion passed')
    }
    rmSync(ws, { recursive: true, force: true })
    process.stdout.write(caseId.padEnd(24) + (problems.length ? 'gate: FAIL\n    ' + problems.join('\n    ') : 'gate: OK') + '\n')
    if (problems.length) failed++
  }
  process.stdout.write(failed === 0 ? '\noracle gate: all cases solvable by construction\n' : '\noracle gate: ' + failed + ' case(s) rejected\n')
  return failed === 0 ? 0 : 1
}

function cmdReport() {
  const files = existsSync(OUT) ? readdirSync(OUT).filter(f => /\.run\d+\.json$/.test(f)) : []
  const runs = files.map(f => readJson(join(OUT, f)))
  const caseIds = [...new Set(runs.map(r => r.case))].sort()
  const table = []
  let totalCost = 0
  for (const caseId of caseIds) {
    const arms = {}
    for (const arm of [...new Set(runs.filter(r => r.case === caseId).map(r => r.arm))]) {
      const list = runs.filter(r => r.case === caseId && r.arm === arm)
      arms[arm] = armStats(list)
      totalCost += list.reduce((a, r) => a + (r.costUsd || 0), 0)
    }
    const w = arms.with_skill, b = arms.without_skill
    table.push({
      case: caseId, arms,
      lift: w && b ? Number((w.resolutionRate - b.resolutionRate).toFixed(3)) : undefined,
      canary: caseId.startsWith('canary-') ? !Object.values(arms).some(a => a.passed > 0) : undefined,
    })
  }
  const lifts = table.filter(t => t.lift !== undefined).map(t => t.lift)
  const summary = {
    generatedAt: new Date().toISOString(),
    engine: 'claude-code',
    cases: table,
    macroLift: lifts.length ? Number((lifts.reduce((a, v) => a + v, 0) / lifts.length).toFixed(3)) : undefined,
    totalCostUsd: Number(totalCost.toFixed(4)),
    canary: table.some(t => t.canary !== undefined) ? (table.some(t => t.canary === false) ? 'BROKEN' : 'ok') : 'absent',
  }
  writeFileSync(join(OUT, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8')
  writeFileSync(join(OUT, 'benchmark.json'), JSON.stringify(benchmarkFromCases(table, { engine: 'claude-code', generatedAt: summary.generatedAt }), null, 2), 'utf8')
  process.stdout.write('=== cc-eval report (engine: claude-code) ===\n')
  for (const t of table) {
    process.stdout.write(t.case + '\n')
    for (const [arm, s] of Object.entries(t.arms)) {
      process.stdout.write('  ' + arm.padEnd(14) + s.passed + '/' + s.runs + ' passed  rate=' + s.resolutionRate +
        '  wilson=[' + s.ci95Wilson.join(',') + ']  pass@k=' + s.passAtK +
        '  turns=' + s.meanTurns + '  wall=' + (s.meanWallMs / 1000).toFixed(1) + 's  $' + s.meanCostUsd + '\n')
    }
    if (t.lift !== undefined) process.stdout.write('  lift=' + t.lift + '\n')
    if (t.canary !== undefined) process.stdout.write('  canary=' + (t.canary ? 'ok (failed as required)' : 'BROKEN') + '\n')
  }
  process.stdout.write('macro lift: ' + summary.macroLift + '\ncanary: ' + summary.canary + '\ntotal cost: $' + summary.totalCostUsd + '\n')
  return 0
}

const { flags, rest } = parseArgs(process.argv.slice(2))
const cmd = rest.shift() || 'report'
let code = 0
if (cmd === 'oracle') code = cmdOracle()
else if (cmd === 'run') code = await cmdRun(flags, rest)
else if (cmd === 'report') code = cmdReport()
else { process.stderr.write('usage: cc-eval oracle|run|report\n'); code = 2 }
process.exitCode = code

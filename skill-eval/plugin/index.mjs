/**
 * DSH multi-turn skill-eval runner.
 *
 * Replaces the shipped one-shot headless runner: creates one Agent, then drives
 * a scripted user through N turns with agent.followup() + agent.whenIdle(),
 * collecting the session event stream and asserting per-turn behaviour.
 *
 * Also bridges the user-questions seam: it mounts the ask_user_question tool and
 * registers a scripted provider, so a question-asking skill runs the same tool
 * path it would in the Web surface.
 *
 * @module @games-robot/dsh-skill-eval-runner
 */
import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { checkFileAssertions } from './assertions.mjs'

export const name = 'skill-eval-runner'

export const inject = ['agentDefaultModel', 'agents', 'sessions']

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function log(line) {
  process.stderr.write('[skill-eval] ' + line + '\n')
}

/** Flat list of tool-call names in one turn's events. */
function toolCallsOf(events, turn) {
  return events.filter(function (e) { return e.type === 'tool/call' && e.data.turn === turn })
}

/** Final assistant text of one turn (concatenated text blocks, last non-empty wins). */
function assistantTextOf(events, turn) {
  var text = ''
  for (var i = 0; i < events.length; i++) {
    var e = events[i]
    if (e.type !== 'assistant/message' || e.data.turn !== turn) continue
    var joined = e.data.message.content.filter(function (b) { return b.type === 'text' })
      .map(function (b) { return b.text }).join('')
    if (joined !== '') text = joined
  }
  return text
}

function usageOf(events, turn) {
  var input = 0, output = 0, cacheRead = 0
  for (var i = 0; i < events.length; i++) {
    var e = events[i]
    if (e.type !== 'assistant/message' || e.data.turn !== turn) continue
    var u = e.data.usage
    if (!u) continue
    input += u.inputTokens || 0
    output += u.outputTokens || 0
    cacheRead += u.cacheReadTokens || 0
  }
  return { inputTokens: input, outputTokens: output, cacheReadTokens: cacheRead }
}

function turnReason(events, turn) {
  for (var i = events.length - 1; i >= 0; i--) {
    var e = events[i]
    if (e.type === 'turn/end' && e.data.turn === turn) return e.data.reason
  }
  return undefined
}

function askedUser(events, turn, text) {
  var calls = toolCallsOf(events, turn)
  for (var i = 0; i < calls.length; i++) {
    if (calls[i].data.name === 'ask_user_question') return true
  }
  return /[?？]/.test(text)
}

/** Slot lookup by keyword match against the model's question text. */
function matchSlots(questionText, slots) {
  var hits = []
  for (var slotName in slots) {
    var slot = slots[slotName]
    var kws = slot.keywords || []
    for (var i = 0; i < kws.length; i++) {
      if (questionText.indexOf(kws[i]) !== -1) { hits.push(slotName); break }
    }
  }
  return hits
}

export function apply(ctx, config) {
  var done = false
  function finish(code) {
    if (done) return
    done = true
    var exit = ctx.get('appExit')
    if (typeof exit === 'function') {
      exit(code)
      // Safety net: the launcher's exit request normally disposes the tree and
      // terminates the process. If some handle keeps the loop alive (watchers,
      // timers), a batch runner must still finish, so force it after a grace
      // period. Unref'd so a healthy shutdown is never delayed.
      setTimeout(function () { process.exit(code) }, 3000).unref()
    } else {
      process.exit(code)
    }
  }

  void run(ctx, config).then(function (code) { finish(code) }, function (error) {
    log('fatal: ' + (error && error.stack ? error.stack : String(error)))
    finish(1)
  })
}

async function run(ctx, config) {
  var startedAt = Date.now()
  var casePath = resolve(config.case)
  var testCase = readJson(casePath)
  var workspace = resolve(config.workspace || testCase.workspace || process.cwd())
  var outPath = resolve(config.out || ('out/' + testCase.id + '.json'))
  mkdirSync(dirname(outPath), { recursive: true })

  await ctx.get('loader')?.await()

  // ---- user-questions bridge -------------------------------------------------
  var answered = []
  var currentTurn = 0
  var uq = ctx.get('userQuestions')
  if (uq !== undefined && config.user_questions !== 'off') {
    try {
      const toolModule = await import('@deepseek-ai/dsh-tool-ask-user')
      await ctx.plugin(toolModule)
      log('mounted tool: ask_user_question')
    } catch (error) {
      log('ask_user_question NOT mounted: ' + (error && error.message ? error.message : String(error)))
    }
    var mode = config.user_questions || 'scripted'
    ctx.effect(function () {
      return uq.registerProvider({
        ask: async function (request) {
          if (mode === 'unavailable') {
            var err = new Error('skill-eval: no human is available in this run')
            err.code = 'NO_PROVIDER'
            throw err
          }
          var answers = (request.questions || []).map(function (q) {
            var hits = matchSlots(String(q.question || '') + ' ' + String(q.detail || ''), testCase.slots || {})
            var slotName = hits.length > 0 ? hits[0] : undefined
            var slot = slotName ? testCase.slots[slotName] : undefined
            answered.push({ turn: currentTurn, question: q.question, slot: slotName, answer: slot ? slot.answer : '' })
            var selected = []
            if (slot && slot.option) selected = [slot.option]
            var custom = slot ? slot.answer : '你来定'
            return { id: q.id, selected: selected, custom: custom }
          })
          return { answers: answers }
        },
      })
    })
  }

  // ---- one agent -------------------------------------------------------------
  var agents = ctx.get('agents')
  var sessions = ctx.get('sessions')
  var defaultModel = ctx.get('agentDefaultModel')
  if (agents === undefined || sessions === undefined || defaultModel === undefined) {
    log('missing core services (agents/sessions/agentDefaultModel)')
    return 1
  }
  const agentModule = await import('@deepseek-ai/dsh-agent')
  const llmModule = await import('@deepseek-ai/dsh-llm')
  const sessionModule = await import('@deepseek-ai/dsh-session')
  var selection = defaultModel.currentSelection()
  var created = await agents.create({
    sessionId: sessionModule.SessionId('session-' + randomUUID()),
    meta: { cwd: workspace },
    agentOptions: { provider: selection.provider, model: selection.model },
    setup: function (agentCtx) {
      agentModule.installModelSelection(agentCtx, { current: selection, assembled: undefined })
    },
  })
  var agent = created.agent
  await agent.whenIdle()

  var events = []
  ctx.on('session/event', function (session, event) {
    if (session !== agent.session) return
    events.push(event)
  })

  // ---- drive turns -----------------------------------------------------------
  var limits = testCase.limits || {}
  var perTurnTimeout = limits.per_turn_timeout_ms || 180000
  var maxTurns = limits.max_turns || (testCase.turns || []).length
  var results = []
  var slotsAnswered = {}
  var scripted = testCase.turns || []

  for (var index = 0; index < scripted.length && index < maxTurns; index++) {
    var spec = scripted[index]
    var userText = spec.user
    for (var slotName in (testCase.slots || {})) {
      userText = userText.split('{{' + slotName + '}}').join(testCase.slots[slotName].answer)
    }
    var turnNumber = agent.session.events.filter(function (e) { return e.type === 'turn/start' }).length + 1
    currentTurn = turnNumber
    log('turn ' + turnNumber + ' <- ' + userText.slice(0, 60))
    agent.followup(llmModule.createUserMessage({
      content: [{ type: 'text', text: userText }],
      source: { kind: 'user' },
    }))
    var timedOut = false
    await Promise.race([
      agent.whenIdle(),
      new Promise(function (r) { setTimeout(function () { timedOut = true; r() }, perTurnTimeout) }),
    ])

    var turnEvents = events.slice()
    var text = assistantTextOf(turnEvents, turnNumber)
    var calls = toolCallsOf(turnEvents, turnNumber).map(function (e) { return e.data.name })
    var assertions = []
    var spec2 = spec.assert || {}

    if (spec2.must_ask_user !== undefined) {
      var asked = askedUser(turnEvents, turnNumber, text)
      assertions.push({ id: 'must_ask_user', passed: asked === spec2.must_ask_user, detail: asked ? 'asked' : 'did not ask' })
    }
    if (spec2.forbid_tools) {
      var used = calls.filter(function (n) { return spec2.forbid_tools.indexOf(n) !== -1 })
      assertions.push({ id: 'forbid_tools', passed: used.length === 0, detail: used.length ? 'used ' + used.join(',') : 'clean' })
    }
    var fileAssertion = checkFileAssertions(workspace, spec2)
    if (fileAssertion) assertions.push(fileAssertion)
    if (spec2.must_not_ask) {
      var asked2 = askedUser(turnEvents, turnNumber, text)
      assertions.push({ id: 'must_not_ask', passed: !asked2, detail: asked2 ? 'asked again' : 'ok' })
    }

    results.push({
      turn: turnNumber,
      asked: askedUser(turnEvents, turnNumber, text),
      tools: calls,
      toolCalls: toolCallsOf(turnEvents, turnNumber).map(function (e) { return { name: e.data.name, arguments: e.data.arguments } }),
      assistantText: text,
      reason: turnReason(turnEvents, turnNumber),
      usage: usageOf(turnEvents, turnNumber),
      timedOut: timedOut,
      assertions: assertions,
    })
    if (timedOut) break
    if (turnReason(turnEvents, turnNumber) && turnReason(turnEvents, turnNumber).kind !== 'completed') break
  }

  await sessions.flush(agent.session)

  var allAssertions = results.reduce(function (acc, r) { return acc.concat(r.assertions) }, [])
  var failed = allAssertions.filter(function (a) { return !a.passed })
  var report = {
    case: testCase.id,
    wallMs: Date.now() - startedAt,
    workspace: workspace,
    sessionId: agent.session.id,
    model: { provider: selection.provider, model: selection.model },
    turnsUsed: results.length,
    maxTurns: maxTurns,
    userQuestionsAnswered: answered,
    totals: {
      inputTokens: results.reduce(function (a, r) { return a + r.usage.inputTokens }, 0),
      outputTokens: results.reduce(function (a, r) { return a + r.usage.outputTokens }, 0),
      cacheReadTokens: results.reduce(function (a, r) { return a + r.usage.cacheReadTokens }, 0),
    },
    passed: failed.length === 0,
    failedAssertions: failed,
    turns: results,
  }
  writeFileSync(outPath, JSON.stringify(report, null, 2), 'utf8')
  log('report -> ' + outPath + ' | passed=' + report.passed + ' turns=' + results.length + ' failed=' + failed.length)
  for (var i = 0; i < results.length; i++) {
    var r = results[i]
    log('  turn ' + r.turn + ': tools=[' + r.tools.join(',') + '] asked=' + r.asked + ' text=' + JSON.stringify(r.assistantText.slice(0, 90)))
  }
  return failed.length === 0 ? 0 : 1
}

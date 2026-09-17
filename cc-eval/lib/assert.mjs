/**
 * Assertions for Claude Code runs.
 *
 * Two families, both fed by the normalized turn view produced by src/runner.mjs:
 *   - turn assertions  : what the agent did in this turn (tool calls, asking, text)
 *   - artifact assertions: what exists on disk afterwards (the world state)
 * Kept dependency-free so the oracle self-test can run the exact same code
 * against a synthesized artifact.
 *
 * @module cc-eval/assert
 */
import { existsSync, readFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import { findFilesByPattern } from './glob.mjs'
export { findFilesByPattern } from './glob.mjs'

/** Tool names that count as "asking the human for input". */
const ASK_TOOLS = ['AskUserQuestion', 'ask_user_question']

/** tool_use blocks recorded for one turn, as {name, input}. */
function callsOf(turn) {
  return (turn.toolCalls || []).filter(c => c.name !== '<<tool_result>>')
}

/**
 * @param turn normalized turn
 * @param mode 'tool' counts only a real AskUserQuestion tool call (strict, used by
 *   must_not_ask); 'text_or_tool' also accepts a question mark in the reply
 *   (permissive, used by must_ask_user so a text-only question is not missed).
 */
export function askedUser(turn, mode = 'text_or_tool') {
  if (callsOf(turn).some(c => ASK_TOOLS.includes(c.name))) return true
  if (mode === 'tool') return false
  return /[?？]/.test(turn.assistantText || '')
}

/**
 * Re-ask detection: a question-marked sentence that mentions one of the keywords
 * means the agent asked again about something it already knows. This is the
 * clause-level check that a bare question mark cannot express.
 */
export function reAskedAbout(turn, keywords) {
  const text = turn.assistantText || ''
  // Only question-marked clauses count; "/[^。！!？?\n]*[？?]/g" keeps the mark so a
  // statement that merely mentions the keyword is not mistaken for a question.
  const questions = text.match(/[^。！!？?\n]*[？?]/g) || []
  const hits = []
  for (const q of questions) for (const kw of keywords) if (q.includes(kw)) hits.push(kw)
  return [...new Set(hits)]
}

export function calledSkill(turn, name) {
  return callsOf(turn).some(c => (c.name === 'Skill' || c.name === 'skill') && (!name || (c.input || '').includes(name)))
}

export function usedTools(turn, names) {
  const used = callsOf(turn).map(c => c.name)
  return names.filter(n => used.includes(n))
}

/**
 * Case-scoped assertions, evaluated AFTER the whole run (they look across turns).
 * Needed because a skill stays loaded for the session: turn 2 does not re-call
 * the Skill tool, so per-turn must_call_skill is the wrong default for multi-turn
 * cases - use must_call_skill_any_turn at case level instead.
 */
export function checkCaseAssertions(turns, spec, workspace) {
  const out = []
  if (!spec) return out
  if (spec.must_call_skill_any_turn) {
    const name = spec.must_call_skill_any_turn
    const hit = turns.some(t => calledSkill(t, name))
    const seen = turns.flatMap(t => callsOf(t).map(c => c.name))
    out.push({ id: 'must_call_skill_any_turn', passed: hit, detail: hit ? 'skill ' + name + ' loaded in some turn' : 'no Skill call in any turn; saw ' + JSON.stringify([...new Set(seen)]) })
  }
  return out
}

/** Assertion spec from a case, evaluated against one normalized turn. */
export function checkTurnAssertions(turn, spec, workspace) {
  const out = []
  if (!spec) return out
  if (spec.must_ask_user !== undefined) {
    const asked = askedUser(turn)
    out.push({ id: 'must_ask_user', passed: asked === spec.must_ask_user, detail: asked ? 'asked' : 'did not ask' })
  }
  if (spec.must_not_ask) {
    const asked = askedUser(turn, spec.must_not_ask === 'text_or_tool' ? 'text_or_tool' : 'tool')
    out.push({ id: 'must_not_ask', passed: !asked, detail: asked ? 'called the question tool again' : 'ok' })
  }
  if (spec.must_not_reask) {
    const hits = reAskedAbout(turn, spec.must_not_reask)
    out.push({ id: 'must_not_reask', passed: hits.length === 0, detail: hits.length ? 're-asked about ' + hits.join(',') : 'ok' })
  }
  if (spec.must_call_skill) {
    const ok = calledSkill(turn, spec.must_call_skill)
    const seen = callsOf(turn).map(c => c.name + (c.input ? ':' + c.input.slice(0, 60) : ''))
    out.push({ id: 'must_call_skill', passed: ok, detail: ok ? 'skill ' + spec.must_call_skill + ' loaded' : 'no Skill call; saw ' + JSON.stringify(seen) })
  }
  if (spec.must_not_call_skill) {
    const any = callsOf(turn).some(c => c.name === 'Skill' || c.name === 'skill')
    out.push({ id: 'must_not_call_skill', passed: !any, detail: any ? 'a skill was loaded' : 'ok' })
  }
  if (spec.must_call_tool) {
    // Complex skills delegate real work to their own CLIs/scripts, so "did the
    // agent follow the workflow" is observable as specific tool invocations.
    // Shape: string | {name, input_contains} | {name, command_contains}.
    // command_contains searches the parsed tool arguments' string values
    // (Bash's command field, Write's file_path, etc.) - more robust than
    // input_contains for JSON-encoded arguments.
    const list = Array.isArray(spec.must_call_tool) ? spec.must_call_tool : [spec.must_call_tool]
    const missing = []
    for (const t of list) {
      const name = typeof t === 'string' ? t : t.name
      const needle = typeof t === 'string' ? null : (t.input_contains || t.command_contains)
      const hit = callsOf(turn).some(c => {
        if (c.name !== name) return false
        if (!needle) return true
        const raw = String(c.input || '')
        // The input may be a JSON-encoded tool_use argument, so search both the
        // raw string and any string value inside the parsed arguments (Bash's
        // command field, Write's file_path field, etc.).
        if (raw.includes(needle)) return true
        try {
          const args = JSON.parse(raw)
          return Object.values(args).some(v => typeof v === 'string' && v.includes(needle))
        } catch { return false }
      })
      if (!hit) missing.push(name + (needle ? '(' + needle + ')' : ''))
    }
    out.push({ id: 'must_call_tool', passed: missing.length === 0, detail: missing.length ? 'not invoked: ' + missing.join(', ') : 'ok' })
  }
  if (spec.forbid_tools) {
    const used = usedTools(turn, spec.forbid_tools)
    out.push({ id: 'forbid_tools', passed: used.length === 0, detail: used.length ? 'used ' + used.join(',') : 'clean' })
  }
  if (spec.must_contain) {
    const missing = spec.must_contain.filter(s => !(turn.assistantText || '').includes(s))
    out.push({ id: 'must_contain', passed: missing.length === 0, detail: missing.length ? 'missing ' + missing.join('|') : 'ok' })
  }
  const file = checkFileAssertions(workspace, spec)
  if (file) out.push(file)
  return out
}

/**
 * Artifact assertions, three targeting modes:
 *   must_write_file           - exact path
 *   must_write_file_pattern   - glob (**, *, ?); real skills emit variable names
 *                               (fe-req-{feature}.md), so exact paths do not fit
 *   must_not_write_file_pattern - absence of a match (boundary cases)
 * must_contain_file is checked against the first match (sorted => deterministic).
 */
export function checkFileAssertions(workspace, spec) {
  if (!spec.must_write_file && !spec.must_write_file_pattern && !spec.must_not_write_file_pattern) return undefined
  if (spec.must_not_write_file_pattern) {
    const hits = findFilesByPattern(workspace, spec.must_not_write_file_pattern)
    return {
      id: 'must_not_write_file_pattern',
      passed: hits.length === 0,
      detail: hits.length ? 'unexpected ' + hits.map(h => basename(h)).slice(0, 3).join(',') : 'ok',
    }
  }
  const id = spec.must_write_file ? 'must_write_file' : 'must_write_file_pattern'
  const targets = spec.must_write_file
    ? (existsSync(join(workspace, spec.must_write_file)) ? [join(workspace, spec.must_write_file)] : [])
    : findFilesByPattern(workspace, spec.must_write_file_pattern)
  if (targets.length === 0) {
    return { id, passed: false, detail: spec.must_write_file ? 'file absent' : 'no file matches ' + spec.must_write_file_pattern }
  }
  const body = readFileSync(targets[0], 'utf8')
  const missing = (spec.must_contain_file || []).filter(s => body.indexOf(s) === -1)
  return {
    id,
    passed: missing.length === 0,
    detail: missing.length ? 'missing ' + missing.join('|') : 'ok (' + targets.length + ' match, first: ' + basename(targets[0]) + ')',
  }
}

/**
 * Shared artifact assertions. Used by the live runner (against the agent's real
 * workspace) and by the oracle self-test (against a synthesised artifact), so a
 * "passing" grader is proven to be reachable, not just assumable.
 *
 * @module skill-eval/assertions
 */
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * @param workspace absolute workspace directory
 * @param spec assertion spec: { must_write_file, must_contain }
 * @returns one assertion result
 */
export function checkFileAssertions(workspace, spec) {
  if (!spec.must_write_file) return undefined
  const target = join(workspace, spec.must_write_file)
  const exists = existsSync(target)
  const body = exists ? readFileSync(target, 'utf8') : ''
  const missing = (spec.must_contain || []).filter(s => body.indexOf(s) === -1)
  return {
    id: 'must_write_file',
    passed: exists && missing.length === 0,
    detail: exists ? (missing.length ? 'missing ' + missing.join('|') : 'ok') : 'file absent',
  }
}

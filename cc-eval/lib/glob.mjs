import { readdirSync } from 'node:fs'
import { join, sep } from 'node:path'

/**
 * Minimal glob matching over workspace-relative forward-slash paths.
 * Supports ** (any depth), * (within one segment) and ? (one char).
 *
 * @module cc-eval/glob
 */
const SPECIAL = '.+^$()|[]{}\\'

/** glob -> RegExp; throws on empty pattern. */
export function globToRegex(pattern) {
  if (!pattern) throw new Error('empty glob pattern')
  let re = '^'
  for (let i = 0; i < pattern.length;) {
    const c = pattern[i]
    if (c === '*') {
      if (pattern[i + 1] === '*') {
        re += '[\\s\\S]*'
        i += 2
        if (pattern[i] === '/') i += 1
      } else {
        re += '[^/]*'
        i += 1
      }
    } else if (c === '?') {
      re += '[^/]'
      i += 1
    } else {
      re += SPECIAL.includes(c) ? '\\' + c : c
      i += 1
    }
  }
  return new RegExp(re + '$')
}

/** All files under workspace matching the glob, sorted for determinism. */
export function findFilesByPattern(workspace, pattern) {
  const rx = globToRegex(pattern)
  const skip = new Set(['node_modules', '.git'])
  const hits = []
  const walk = dir => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (skip.has(e.name)) continue
      const full = join(dir, e.name)
      if (e.isDirectory()) walk(full)
      else {
        const rel = full.slice(workspace.length + 1).split(sep).join('/')
        if (rx.test(rel)) hits.push(full)
      }
    }
  }
  walk(workspace)
  return hits.sort()
}

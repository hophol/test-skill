#!/usr/bin/env node
/** Validate breakdown.json. Exit 0 = pass; exit 1 with a problem list. */
import fs from 'node:fs'

const file = process.argv[2] || 'breakdown.json'
if (!fs.existsSync(file)) {
  console.error('breakdown.json not found: ' + file)
  process.exit(1)
}
let data
try { data = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')) } catch (e) {
  console.error('breakdown.json is not valid JSON: ' + e.message)
  process.exit(1)
}
const problems = []
const acs = Array.isArray(data.acs) ? data.acs : []
const tasks = Array.isArray(data.tasks) ? data.tasks : []
if (!data.us_title) problems.push('missing us_title')
if (acs.length === 0) problems.push('no acceptance criteria (acs[])')
if (tasks.length === 0) problems.push('no tasks[]')
const acIds = new Set(acs.map(a => a.id))
for (const a of acs) if (!a.id || !a.text) problems.push('ac missing id/text: ' + JSON.stringify(a))
for (const t of tasks) {
  if (!t.id) problems.push('task missing id')
  if (!t.title) problems.push('task ' + (t.id || '?') + ' missing title')
  if (!acIds.has(t.ac)) problems.push('task ' + (t.id || '?') + ' references unknown ac: ' + t.ac)
  const est = Number(t.estimate_days)
  if (!(est > 0 && est <= 1)) problems.push('task ' + (t.id || '?') + ' estimate_days must be in (0, 1]')
  if (!t.test_hint || !String(t.test_hint).trim()) problems.push('task ' + (t.id || '?') + ' missing test_hint')
}
for (const id of acIds) {
  if (!tasks.some(t => t.ac === id)) problems.push('acceptance criterion ' + id + ' has no task')
}
if (problems.length > 0) {
  console.error('VALIDATION FAILED (' + problems.length + '):')
  for (const p of problems) console.error('  - ' + p)
  process.exit(1)
}
console.log('OK: ' + acs.length + ' ACs covered by ' + tasks.length + ' tasks')

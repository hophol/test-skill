#!/usr/bin/env node
/** US markdown -> structured JSON. Exit codes: 0 ok, 1 usage/no AC found. */
import fs from 'node:fs'

const file = process.argv[2]
if (!file || !fs.existsSync(file)) {
  console.error('usage: node us_parser.mjs <us.md>')
  process.exit(1)
}
const text = fs.readFileSync(file, 'utf8')
const lines = text.split(/\r?\n/)

const title = (lines.find(l => l.startsWith('#')) || '').replace(/^#+\s*/, '').trim()
const story = text.match(/作为\s*(.+?)\s*[，,]?\s*我想要\s*(.+?)\s*[，,]?\s*(以便|这样)/s)
  || text.match(/As an?\s*(.+?)\s*,?\s*I want\s*(.+?)\s*,?\s*so that\s*(.+)/is)
const role = story ? story[1].trim() : ''
const goal = story ? story[2].trim() : ''
const benefit = story && story[3] ? story[3].replace(/^(以便|这样|so that)\s*/i, '').trim() : ''

const acs = []
let n = 0
for (const line of lines) {
  const m = line.match(/^\s*(?:[-*]|\d+[.、])\s*(?:\[(.*?)\]\s*)?(?:AC\s*(\d+)[.::、]\s*|验收标准\s*(\d+)[.::、]\s*)?(.+)$/)
  if (!m) continue
  const body = (m[4] || '').trim()
  if (!body) continue
  // 显式编号（AC3: / 验收标准 2.）的行直接收录；无编号的行才按关键词过滤
  const numbered = Boolean(m[2] || m[3])
  if (!numbered && !/^(Given|When|Then|如果|当|应当|应该|可以|能够|系统|页面|用户)/i.test(body)) continue
  n += 1
  acs.push({ id: 'AC' + (m[2] || m[3] || n), text: body })
}
if (acs.length === 0) {
  console.error('no acceptance criteria found (expected lines starting with AC1./验收标准/Given/When/应当...)')
  process.exit(1)
}
console.log(JSON.stringify({ title, role, goal, benefit, acceptance_criteria: acs }, null, 2))

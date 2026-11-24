import test from 'node:test'
import assert from 'node:assert/strict'
import { validateContact } from '../code/personal-agent-os/adapters/opencode/index.mjs'

const target = { project: '3004', home: 'S042' }
const base = { configured: true, runtime: 'opencode', native_session_id: 'ses_ok' }

test('normal OpenCode Contact accepts a nullable STOP path when not stopped', () => {
  const row = validateContact({ ...base, stop_present: false, stop_file: null }, target, 'ses_ok')
  assert.equal(row.stop_file, null)
  assert.equal(validateContact({ ...base, stop_present: false, stop_file: '' }, target, 'ses_ok').stop_file, null)
})

test('a registered STOP path is preserved', () => {
  const row = validateContact({ ...base, stop_present: false, stop_file: '/tmp/STOP' }, target, 'ses_ok')
  assert.equal(row.stop_file, '/tmp/STOP')
})

test('stopped without a locator and uncertain values are rejected', () => {
  assert.throws(() => validateContact({ ...base, stop_present: true, stop_file: null }, target, 'ses_ok'))
  assert.throws(() => validateContact({ ...base, stop_present: 'yes', stop_file: null }, target, 'ses_ok'))
  assert.throws(() => validateContact({ ...base, stop_present: false, stop_file: 7 }, target, 'ses_ok'))
})

test('wrong session and runtime are rejected', () => {
  assert.throws(() => validateContact({ ...base, native_session_id: 'ses_other', stop_present: false }, target, 'ses_ok'))
  assert.throws(() => validateContact({ ...base, runtime: 'dsh', stop_present: false }, target, 'ses_ok'))
})

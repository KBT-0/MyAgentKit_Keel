// The myagentkit-suggestion mod: when it checks, what it hands the ledger, and when it stays quiet.
import { expect, test } from 'claude-code/testing'
import { parseNote } from '../hooks/register.js'

const NOTE = { claim: 'The agent edited the test after it failed.', evidence: 'tests/t.py:4 "== 3" became ">= 1"',
  confidence: 'high', check: 'git diff -- tests/t.py', topic: 'loosened test' }
const USAGE = { input_tokens: 3, output_tokens: 40, cache_read_input_tokens: 90000, cache_creation_input_tokens: 200 }

type Calls = { argv: string[][]; stdin: string[]; forks: string[]; logs: string[] }

// Stubs for everything the mod asks Claude Code; `gate` and `fork` shape the answers.
function stubs(on, calls: Calls, opts: { role?: string; gate?: object; fork?: string | null; limit?: number } = {}) {
  const gate = { enabled: true, stopped: false, interval: 1, known: [], recent: [], ...(opts.gate ?? {}) }
  on('session.start', () => ({ cwd: '/work' }))
  on('env.get', () => ({ value: opts.role }))
  on('session.root', () => ({ value: '/work' }))
  on('fs.exists', () => ({ value: true }))
  on('session.id', () => ({ value: 's1' }))
  on('session.usage', () => ({ value: { rateLimits: [{ kind: 'five_hour', percentUsed: opts.limit ?? 10 }] } }))
  on('process.run', ($, e) => {
    calls.argv.push(e.argv)
    if (e.init?.stdin) calls.stdin.push(e.init.stdin)
    const mode = e.argv[3]
    const stdout = mode === 'gate' ? JSON.stringify(gate) : mode === 'add-note' ? '7\n' : 'myagentkit-suggestion: suggestions: ' + mode
    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('model.fork', ($, e) => {
    calls.forks.push(e.prompt)
    return { value: opts.fork === null ? null : { text: opts.fork ?? JSON.stringify(NOTE), usage: USAGE } }
  })
  on('ui.log', ($, e) => {
    calls.logs.push(e.text)
    return { value: undefined }
  })
  on('tool.call', () => ({ result: 'ok' }))
}

const settle = async () => {
  for (let i = 0; i < 200; i += 1) await Promise.resolve()
}

async function start($) {
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
}

async function calls($, n: number, extra: object = {}) {
  for (let i = 0; i < n; i += 1) {
    await $.tool.call({ tool: 'Bash', command: 'echo ' + i, ...extra })
    await settle()
  }
}

const fresh = (): Calls => ({ argv: [], stdin: [], forks: [], logs: [] })

test('ten main-loop tool calls run one side check, and its note goes to the ledger and the chat', async ($, on) => {
  const c = fresh()
  stubs(on, c)
  await start($)
  await calls($, 9)
  expect(c.forks.length).toBe(0)
  await calls($, 1)
  expect(c.forks.length).toBe(1)
  expect(c.forks[0]).toContain('Default to abstaining.')
  expect(c.forks[0]).toContain('Why this check runs now: periodic')
  const row = JSON.parse(c.stdin[0])
  expect(row).toMatchObject({ session: 's1', trigger: 'periodic', claim: NOTE.claim, usage: USAGE })
  expect(c.argv.find((a) => a[3] === 'add-note')?.slice(0, 3)).toEqual(['sh', '/work/.claude/hooks/py.sh',
    '/work/.claude/hooks/suggestions.py'])
  expect(c.logs).toEqual(['myagentkit-suggestion #7: ' + NOTE.claim])
})

test('an abstain is recorded with its tokens and shows nothing', async ($, on) => {
  const c = fresh()
  stubs(on, c, { fork: '{"abstain": true}' })
  await start($)
  await calls($, 10)
  expect(JSON.parse(c.stdin[0])).toMatchObject({ abstain: true, usage: USAGE })
  expect(c.logs).toEqual([])
})

test('the same action three times checks at once, before ten calls', async ($, on) => {
  const c = fresh()
  stubs(on, c)
  await start($)
  for (let i = 0; i < 3; i += 1) {
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    await settle()
  }
  expect(c.forks.length).toBe(1)
  expect(c.forks[0]).toContain('the same action 3 times: Bash "npm test"')
})

test('a note buys three quiet calls, and a quiet stretch needs ten more calls', async ($, on) => {
  const c = fresh()
  stubs(on, c)
  await start($)
  await calls($, 10)
  await calls($, 9)
  expect(c.forks.length).toBe(1)
  await calls($, 1)
  expect(c.forks.length).toBe(2)
})

test('a worker session runs no side check', async ($, on) => {
  const c = fresh()
  stubs(on, c, { role: 'worker' })
  await start($)
  await calls($, 12)
  expect(c.forks.length).toBe(0)
})

test('a sub-agent\'s calls do not count', async ($, on) => {
  const c = fresh()
  stubs(on, c)
  await start($)
  await calls($, 12, { agentId: 'a1' })
  expect(c.forks.length).toBe(0)
})

test('the owner\'s off switch skips the fork', async ($, on) => {
  const c = fresh()
  stubs(on, c, { gate: { enabled: false } })
  await start($)
  await calls($, 12)
  expect(c.forks.length).toBe(0)
})

test('a plan limit at 80% skips the fork', async ($, on) => {
  const c = fresh()
  stubs(on, c, { limit: 85 })
  await start($)
  await calls($, 12)
  expect(c.forks.length).toBe(0)
})

test('a halved precision doubles the interval', async ($, on) => {
  const c = fresh()
  stubs(on, c, { gate: { interval: 2, known: ['loosened test'], recent: ['An older claim.'] } })
  await start($)
  await calls($, 19)
  expect(c.forks.length).toBe(0)
  await calls($, 1)
  expect(c.forks.length).toBe(1)
  expect(c.forks[0]).toContain('Known topics (do not repeat): loosened test')
  expect(c.forks[0]).toContain('Recent notes: An older claim.')
})

test('a failed fork fails open', async ($, on) => {
  const c = fresh()
  stubs(on, c, { fork: null })
  await start($)
  await calls($, 10)
  expect(c.stdin).toEqual([])
  expect(c.logs).toEqual([])
})

test('/myagentkit:suggestions off runs the ledger switch and prints its answer', async ($, on) => {
  const c = fresh()
  stubs(on, c)
  await start($)
  const answer = await $.command.run({ command: 'myagentkit:suggestions', args: 'off' })
  expect(c.argv.at(-1)?.slice(3)).toEqual(['off'])
  expect(answer.text).toBe('myagentkit-suggestion: suggestions: off')
  await $.command.run({ command: 'myagentkit:suggestions', args: '' })
  expect(c.argv.at(-1)?.slice(3)).toEqual(['status'])
})

test('a note needs evidence, a check and high or medium confidence', async () => {
  expect(parseNote('Sure: ' + JSON.stringify(NOTE))).toEqual(NOTE)
  expect(parseNote(JSON.stringify({ ...NOTE, evidence: '' }))).toBe(null)
  expect(parseNote(JSON.stringify({ ...NOTE, confidence: 'low' }))).toBe(null)
  expect(parseNote('{"abstain": true}')).toBe(null)
  expect(parseNote('no json')).toBe(null)
})

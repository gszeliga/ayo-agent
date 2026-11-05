import { formatBytes, formatUtc, relativeTime } from './format'

const NOW = Date.parse('2026-11-05T12:00:00Z')
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString()

test.each([
  [0, 'just now'],
  [59, 'just now'],
  [-30, 'just now'], // a clock slightly behind the server's
  [60, '1 min ago'],
  [59 * 60 + 59, '59 min ago'],
  [3600, '1 h ago'],
  [23 * 3600 + 3599, '23 h ago'],
  [86400, '1 d ago'],
  [29 * 86400, '29 d ago'],
  [30 * 86400, '6 Oct 2026'],
])('%i s ago reads %j', (seconds, expected) => {
  expect(relativeTime(ago(seconds), NOW)).toBe(expected)
})

test('the exact time is UTC to the minute', () => {
  expect(formatUtc('2026-11-05T10:14:03.123+01:00')).toBe('2026-11-05 09:14 UTC')
})

test.each([
  [0, '0 B'],
  [1023, '1023 B'],
  [1024, '1.0 KB'],
  [4300, '4.2 KB'],
  [5 * 1024 * 1024, '5.0 MB'],
])('%i bytes is %j', (bytes, expected) => {
  expect(formatBytes(bytes)).toBe(expected)
})

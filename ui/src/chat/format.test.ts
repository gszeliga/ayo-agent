import { formatCost, formatDuration, formatTokens } from './format'

test.each([
  [0, '$0.00'],
  [0.00004, '<$0.0001'],
  [0.0021, '$0.0021'],
  [0.00999, '$0.0100'],
  [0.0123, '$0.01'],
  [1.5, '$1.50'],
])('cost %d reads %s', (cost, text) => {
  expect(formatCost(cost)).toBe(text)
})

test.each([
  [1, '1 token'],
  [850, '850 tokens'],
  [1000, '1k tokens'],
  [12_345, '12.3k tokens'],
  [1_250_000, '1.3M tokens'],
])('%d tokens read %s', (tokens, text) => {
  expect(formatTokens(tokens)).toBe(text)
})

test.each([
  [850.4, '850 ms'],
  [4500, '4.5 s'],
  [12_400, '12 s'],
])('%d ms reads %s', (ms, text) => {
  expect(formatDuration(ms)).toBe(text)
})

describe('in Spanish', () => {
  test.each([
    [0, '0,00 $'],
    [0.00004, '<0,0001 $'],
    [0.0021, '0,0021 $'],
    [1.5, '1,50 $'],
  ])('cost %d reads %s', (cost, text) => {
    expect(formatCost(cost, 'es')).toBe(text)
  })

  test.each([
    [1, '1 token'],
    [850, '850 tokens'],
    [1000, '1k tokens'],
    [12_345, '12,3k tokens'],
    [1_250_000, '1,3M tokens'],
  ])('%d tokens read %s', (tokens, text) => {
    expect(formatTokens(tokens, 'es')).toBe(text)
  })

  test.each([
    [850.4, '850 ms'],
    [4500, '4,5 s'],
    [12_400, '12 s'],
  ])('%d ms reads %s', (ms, text) => {
    expect(formatDuration(ms, 'es')).toBe(text)
  })
})

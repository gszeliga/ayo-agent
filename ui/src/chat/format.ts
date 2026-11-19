/** A cost in US dollars: two decimals from a cent up, four below, "<$0.0001" for less. */
export function formatCost(cost: number): string {
  if (cost === 0) return '$0.00'
  if (cost < 0.0001) return '<$0.0001'
  return `$${cost.toFixed(cost < 0.01 ? 4 : 2)}`
}

/** "850 tokens", "12.3k tokens", "1.2M tokens". */
export function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${String(tokens)} ${tokens === 1 ? 'token' : 'tokens'}`
  if (tokens < 1_000_000) return `${trim(tokens / 1000)}k tokens`
  return `${trim(tokens / 1_000_000)}M tokens`
}

function trim(value: number): string {
  return value.toFixed(1).replace(/\.0$/, '')
}

export function plural(count: number, one: string, many: string): string {
  return `${String(count)} ${count === 1 ? one : many}`
}

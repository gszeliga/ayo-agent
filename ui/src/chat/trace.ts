import type { components } from '@/api/schema'

import { formatCost, formatTokens, plural } from './format'

type CaseDetail = components['schemas']['CaseDetail']
type CaseTrace = components['schemas']['CaseTrace']
type LLMUsage = components['schemas']['LLMUsage']

/** What a turn's badges say: a capped turn, a failed retrieval, refused tool calls. */
export function traceFlags(trace: CaseTrace): {
  capped: boolean
  retrievalFailed: boolean
  refused: number
} {
  return {
    capped: trace.capped,
    retrievalFailed: trace.retrieval_error !== null,
    refused: trace.tool_calls.filter((call) => !call.ok).length,
  }
}

function minus(total: number | null, part: number | null): number | null {
  if (total === null || part === null) return total
  return Math.max(0, total - part)
}

/**
 * The turns' share of the case's usage: the case total less its AI summary (the API sums
 * both). A figure only the summary reported reads as 0 here; the totals can't tell apart.
 */
export function turnsUsage(detail: CaseDetail): LLMUsage {
  const summary = detail.summary?.usage
  const total = detail.usage
  if (!summary) return total
  return {
    llm_calls: Math.max(0, total.llm_calls - summary.llm_calls),
    prompt_tokens: minus(total.prompt_tokens, summary.prompt_tokens),
    completion_tokens: minus(total.completion_tokens, summary.completion_tokens),
    total_tokens: minus(total.total_tokens, summary.total_tokens),
    cost: minus(total.cost, summary.cost),
  }
}

/** "3 calls · 8.3k tokens · $0.0027", leaving out what was not reported. */
export function usageLine(usage: LLMUsage): string {
  return [
    plural(usage.llm_calls, 'call', 'calls'),
    ...(usage.total_tokens !== null ? [formatTokens(usage.total_tokens)] : []),
    ...(usage.cost !== null ? [formatCost(usage.cost)] : []),
  ].join(' · ')
}

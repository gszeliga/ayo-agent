import type { components } from '@/api/schema'
import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

import { formatCost, formatTokens } from './format'

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

/**
 * "3 calls · 8.3k tokens · $0.0027", leaving out what was not reported ("3 llamadas · 8,3k
 * tokens · 0,0027 $" in Spanish).
 */
export function usageLine(usage: LLMUsage, language: Language): string {
  const t = i18n.getFixedT(language, 'chat')
  return [
    t('usage.calls', { count: usage.llm_calls }),
    ...(usage.total_tokens !== null ? [formatTokens(usage.total_tokens, language)] : []),
    ...(usage.cost !== null ? [formatCost(usage.cost, language)] : []),
  ].join(' · ')
}

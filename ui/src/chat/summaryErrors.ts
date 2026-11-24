import { ApiError } from '@/api/errors'

/**
 * What went wrong with a summary, as a code worded when shown (`chat.summaryError.*`), so a
 * language switch rewords an error already on screen. `modelFailed` carries the API's error
 * code; `other` the error itself (worded by `describeError`). Nothing is stored on a
 * failure: an earlier summary stays.
 */
export type SummaryProblem =
  | { code: 'unreachable' | 'empty' | 'notFound' | 'noModel' }
  | { code: 'modelFailed'; type: string }
  | { code: 'other'; error: Error }

export function describeSummaryError(error: Error): SummaryProblem {
  if (!(error instanceof ApiError)) return { code: 'other', error }
  if (error.isNetworkError) return { code: 'unreachable' }
  if (error.status === 409 && error.type === 'case_empty') return { code: 'empty' }
  if (error.status === 404) return { code: 'notFound' }
  if (error.status === 502) return { code: 'modelFailed', type: error.type ?? 'llm_error' }
  if (error.status === 503) return { code: 'noModel' }
  return { code: 'other', error }
}

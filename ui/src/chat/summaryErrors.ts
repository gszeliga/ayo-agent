import { ApiError } from '@/api/errors'

/** What to say about a failed summary. Nothing is stored then: an earlier one stays. */
export function describeSummaryError(error: Error): string {
  if (!(error instanceof ApiError)) return error.message
  if (error.isNetworkError) {
    return "Can't reach the API, so the summary may still have been made: refresh the case to see."
  }
  if (error.status === 409 && error.type === 'case_empty') {
    return 'This case has no turns yet: there is nothing to summarise. No call was made.'
  }
  if (error.status === 404) return 'This case no longer exists.'
  if (error.status === 502) {
    return `The language model failed (${error.type ?? 'llm_error'}), so nothing was stored. You can try again.`
  }
  if (error.status === 503) {
    return 'The API has no language model configured (OPENROUTER_API_KEY). No call was made.'
  }
  return error.message
}

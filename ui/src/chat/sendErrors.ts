import { ApiError } from '@/api/errors'

type Action = 'send-again' | 'reload' | null

/** What to say about a failed send, and what to offer. Nothing of a failed turn is stored. */
export function describeSendError(error: Error): { message: string; action: Action } {
  if (!(error instanceof ApiError)) return { message: error.message, action: 'send-again' }
  if (error.isNetworkError) {
    return {
      message:
        "Can't reach the API, so the message may not have arrived. Send it again, or reload the case to see whether it did.",
      action: 'send-again',
    }
  }
  if (error.status === 409 && error.type === 'case_closed') {
    return { message: 'This case is closed: it takes no more messages.', action: 'reload' }
  }
  if (error.status === 409) {
    return {
      message:
        'Another message in this conversation was saved while yours was being answered. Nothing of yours was stored: reload the case, then send it again.',
      action: 'reload',
    }
  }
  if (error.status === 422) {
    return { message: `The API refused the message: ${error.message}`, action: null }
  }
  if (error.status === 502) {
    return {
      message: 'The language model failed, so nothing was stored. You can send it again.',
      action: 'send-again',
    }
  }
  if (error.status === 503) {
    return {
      message:
        'The API has no language model configured (OPENROUTER_API_KEY), so nothing was stored.',
      action: null,
    }
  }
  return { message: error.message, action: 'send-again' }
}

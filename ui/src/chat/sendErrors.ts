import { ApiError } from '@/api/errors'

type Action = 'send-again' | 'reload' | null

/**
 * What went wrong with a send, as a code worded when shown (`chat.sendError.*`), so a
 * language switch rewords an error already on screen. `refused` carries the API's `msg`;
 * `other` the error itself (worded by `describeError`).
 */
export type SendProblem =
  | { code: 'unreachable' | 'caseClosed' | 'conflict' | 'modelFailed' | 'noModel' }
  | { code: 'refused'; message: string }
  | { code: 'other'; error: Error }

/** What to say about a failed send, and what to offer. Nothing of a failed turn is stored. */
export function describeSendError(error: Error): { problem: SendProblem; action: Action } {
  if (!(error instanceof ApiError))
    return { problem: { code: 'other', error }, action: 'send-again' }
  if (error.isNetworkError) return { problem: { code: 'unreachable' }, action: 'send-again' }
  if (error.status === 409 && error.type === 'case_closed') {
    return { problem: { code: 'caseClosed' }, action: 'reload' }
  }
  if (error.status === 409) return { problem: { code: 'conflict' }, action: 'reload' }
  if (error.status === 422) {
    return { problem: { code: 'refused', message: error.message }, action: null }
  }
  if (error.status === 502) return { problem: { code: 'modelFailed' }, action: 'send-again' }
  if (error.status === 503) return { problem: { code: 'noModel' }, action: null }
  return { problem: { code: 'other', error }, action: 'send-again' }
}

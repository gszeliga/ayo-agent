import type { components } from '@/api/schema'

type CaseDetail = components['schemas']['CaseDetail']

/** Why a case cannot be continued here, worded when shown (`chat.readOnly.*`). */
export type ReadOnlyReason = 'closed' | 'otherChannel'

/** Why a case cannot be continued here (decision 19), or null when it can. */
export function readOnlyReason(detail: CaseDetail): ReadOnlyReason | null {
  if (detail.closed_at !== null || detail.phase === 'closed') return 'closed'
  if (detail.web_session_id === null) return 'otherChannel'
  return null
}

import type { components } from '@/api/schema'

type CaseDetail = components['schemas']['CaseDetail']

/** Why a case cannot be continued here (decision 19), or null when it can. */
export function readOnlyReason(detail: CaseDetail): string | null {
  if (detail.closed_at !== null || detail.phase === 'closed') {
    return 'This case is closed: it can be read here but not continued.'
  }
  if (detail.web_session_id === null) {
    return 'This case came from another channel: it can be read here but not continued.'
  }
  return null
}

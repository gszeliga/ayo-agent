import type { components } from '@/api/schema'

export type Phase = components['schemas']['CaseListItem']['phase']

/** The phases in the order a case moves through them, `closed` last. */
export const PHASES: readonly Phase[] = [
  'understand',
  'challenge',
  'analyse',
  'action',
  'followup',
  'closed',
]

export const PHASE_LABELS: Record<Phase, string> = {
  understand: 'Understand',
  challenge: 'Challenge',
  analyse: 'Analyse',
  action: 'Action',
  followup: 'Follow-up',
  closed: 'Closed',
}

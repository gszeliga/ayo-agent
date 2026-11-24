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
// Their names are in the `chat` catalog by value (`chat.phase.*`).

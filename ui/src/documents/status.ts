import type { components } from '@/api/schema'
import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

export type OutdatedReason = NonNullable<components['schemas']['Document']['outdated_reason']>

/** Every `outdated_reason`, in the order they are listed. */
export const OUTDATED_REASONS: readonly OutdatedReason[] = [
  'chunker_changed',
  'embedder_changed',
  'unknown',
]

/** `outdated_reason` in words. */
export function outdatedReasonLabel(reason: OutdatedReason, language: Language): string {
  return i18n.getFixedT(language, 'documents')(`outdatedReason.${reason}`)
}

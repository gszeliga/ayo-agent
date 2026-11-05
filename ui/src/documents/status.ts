import type { components } from '@/api/schema'

type OutdatedReason = NonNullable<components['schemas']['Document']['outdated_reason']>

/** `outdated_reason` in words. */
export const OUTDATED_REASONS: Record<OutdatedReason, string> = {
  chunker_changed: 'Chunking settings changed since it was indexed',
  embedder_changed: 'Embedding model or size changed since it was indexed',
  unknown: 'Indexed before settings were recorded',
}

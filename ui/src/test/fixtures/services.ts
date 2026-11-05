import type { components } from '@/api/schema'

type ServiceHealth = components['schemas']['ServiceHealth']
type IndexingSettings = components['schemas']['IndexingSettings']

/** A healthy local API with the fake embedder, as `GET /admin/health` returns it. */
export function makeHealth(
  overrides: {
    database?: Partial<ServiceHealth['database']>
    embeddings?: Partial<ServiceHealth['embeddings']>
  } = {},
): ServiceHealth {
  const database = { status: 'up' as const, latency_ms: 3, error: null, ...overrides.database }
  const embeddings = {
    status: 'up' as const,
    provider: 'voyage' as const,
    checked_at: new Date(Date.now() - 20_000).toISOString(),
    latency_ms: 180,
    error: null,
    cached: false,
    last_success_at: new Date(Date.now() - 3600_000).toISOString(),
    last_error_at: null,
    last_error: null,
    ...overrides.embeddings,
  }
  return {
    status: database.status === 'up' && embeddings.status === 'up' ? 'ok' : 'degraded',
    database,
    embeddings,
  }
}

export const CHUNKER_CONFIG =
  'md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1'

/** `GET /admin/settings` with the defaults; matches the document fixtures' configs. */
export function makeSettings(overrides: Partial<IndexingSettings> = {}): IndexingSettings {
  return {
    chunking: {
      chunker_version: 'md-header+recursive@v3',
      chunk_size: 800,
      chunk_overlap: 80,
      min_chunk_size: 100,
      chunker_config: CHUNKER_CONFIG,
    },
    embedding: {
      provider: 'voyage',
      model: 'voyage-4',
      dimensions: 1024,
      batch_size: 128,
      embedder_config: 'voyage-4/document/1024',
    },
    uploads: { max_upload_bytes: 5 * 1024 * 1024 },
    documents: {
      total: 12,
      indexed: 9,
      outdated: { unknown: 0, chunker_changed: 2, embedder_changed: 1 },
    },
    ...overrides,
  }
}

import type { components } from '@/api/schema'

type Document = components['schemas']['Document']
type TenantSummary = components['schemas']['TenantSummary']

const HOUR = 3600 * 1000

let counter = 0

/** A stored document like the API returns it; `hoursAgo` sets `updated_at` from the real clock. */
export function makeDocument(overrides: Partial<Document> & { hoursAgo?: number } = {}): Document {
  const { hoursAgo = 3, ...fields } = overrides
  counter += 1
  const updated = new Date(Date.now() - hoursAgo * HOUR).toISOString()
  return {
    doc_id: `upload-${counter.toString(16).padStart(12, '0')}`,
    tenant: 'planta-norte',
    title: 'PRO-014 Control de sellado',
    source_key: 'pro-014-control-sellado.md',
    status: 'indexed',
    outdated_reason: null,
    chunk_count: 12,
    size_bytes: 4300,
    content_hash: 'a'.repeat(64),
    chunk_signature: 'b'.repeat(64),
    embed_signature: 'c'.repeat(64),
    chunker_config: 'md-header+recursive@v3/size=800/overlap=80/min=100',
    embedder_config: 'voyage-4/document/1024',
    created_at: updated,
    updated_at: updated,
    chunked_at: updated,
    embedded_at: updated,
    ...fields,
  }
}

export const DOCUMENTS: Document[] = [
  makeDocument({ hoursAgo: 3 }),
  makeDocument({
    title: 'Manual de mantenimiento de la caldera B2',
    source_key: 'manual-caldera-b2.md',
    status: 'outdated',
    outdated_reason: 'chunker_changed',
    chunk_count: 48,
    size_bytes: 52_000,
    hoursAgo: 30,
  }),
  makeDocument({
    tenant: 'planta-sur',
    title: 'Procedimiento de arranque de la línea 3',
    source_key: 'arranque-linea-3.md',
    chunk_count: 7,
    size_bytes: 900,
    hoursAgo: 0.1,
  }),
]

export const TENANTS: TenantSummary[] = [
  { tenant: 'planta-norte', document_count: 2, chunk_count: 60 },
  { tenant: 'planta-sur', document_count: 1, chunk_count: 7 },
]

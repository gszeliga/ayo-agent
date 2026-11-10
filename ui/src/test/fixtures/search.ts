import type { components } from '@/api/schema'

import { CHUNKER_CONFIG } from './services'

type SearchHitResult = components['schemas']['SearchHitResult']
type SearchResponse = components['schemas']['SearchResponse']

export const QUESTION = '¿Qué presión mínima debe tener la junta de la bomba?'

const LONG_TEXT = [
  '1. Comprobar la presión de la junta con el manómetro de referencia y anotar el valor.',
  '2. Si la presión baja de 2,5 bar, aislar la bomba y avisar a mantenimiento.',
  '3. Revisar visualmente el goteo del cierre; más de 5 gotas por minuto es fuga.',
  '4. Firmar la hoja de turno con la hora de la comprobación.',
].join('\n')

export function makeHit(overrides: Partial<SearchHitResult> = {}): SearchHitResult {
  return {
    rank: 1,
    similarity: 0.8734,
    chunk_id: '0b9f6c1e-3d2a-4f5b-8c7d-9e0a1b2c3d4e',
    chunk_index: 2,
    heading: 'PRO-014 Control de sellado > 3. Pasos',
    chunk_text: LONG_TEXT,
    char_count: LONG_TEXT.length,
    doc_id: 'upload-3f9a1c2b7d4e',
    document_title: 'PRO-014 Control de sellado',
    source_key: 'pro-014-control-sellado.md',
    tenant: 'planta-norte',
    embedder_outdated: false,
    ...overrides,
  }
}

export const HITS: SearchHitResult[] = [
  makeHit(),
  makeHit({
    rank: 2,
    similarity: 0.6125,
    chunk_id: '1c0a7d2f-4e3b-4a6c-9d8e-0f1a2b3c4d5e',
    chunk_index: 23,
    heading: null,
    chunk_text: 'Bombas P-101 a P-108 de la línea de envasado.',
    char_count: 45,
    doc_id: 'upload-a1b2c3d4e5f6',
    document_title: null,
    source_key: 'man-102-bomba-centrifuga.md',
    tenant: 'planta-sur',
    embedder_outdated: true,
  }),
]

/** `POST /admin/search` with debug on, for `query`. */
export function makeSearchResponse(
  overrides: Partial<SearchResponse> & { query?: string } = {},
): SearchResponse {
  const query = overrides.query ?? QUESTION
  return {
    query,
    results: HITS,
    skipped: { embedder_mismatch: 0 },
    debug: {
      embedded_query: query,
      input_type: 'query',
      embedder_config: 'voyage-4/document/1024',
      chunker_config: CHUNKER_CONFIG,
      timings_ms: { embed: 41.2, search: 6.3, total: 47.5 },
    },
    ...overrides,
  }
}

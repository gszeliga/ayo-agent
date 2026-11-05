import type { components, paths } from './schema'

type SettingsOk = paths['/admin/settings']['get']['responses'][200]['content']['application/json']

// Compile-time checks (`pnpm typecheck`): the generated types match the API contract.
const settings: SettingsOk = {
  chunking: {
    chunker_version: 'md-header+recursive@v3',
    chunk_size: 800,
    chunk_overlap: 80,
    min_chunk_size: 100,
    chunker_config: 'md-header+recursive@v3/size=800',
  },
  embedding: {
    provider: 'voyage',
    model: 'voyage-4',
    dimensions: 1024,
    batch_size: 128,
    embedder_config: 'voyage-4/document/1024',
  },
  uploads: { max_upload_bytes: 5242880 },
  documents: {
    total: 1,
    indexed: 1,
    outdated: { unknown: 0, chunker_changed: 0, embedder_changed: 0 },
  },
}
const status: components['schemas']['Document']['status'] = 'outdated'

test('the generated types describe the API', () => {
  // @ts-expect-error: `provider` is a closed set in the contract.
  const wrong: components['schemas']['EmbeddingSettings']['provider'] = 'openai'

  expect([settings.documents.total, status, wrong]).toEqual([1, 'outdated', 'openai'])
})

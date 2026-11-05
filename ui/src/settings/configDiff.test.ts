import openapi from '../../../docs/openapi.json'

import {
  chunkerDiff,
  differsNote,
  embedderDiff,
  parseChunkerConfig,
  parseEmbedderConfig,
} from './configDiff'

const CURRENT =
  'md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1'

test("the format matches the API's examples", () => {
  const schemas = openapi.components.schemas
  const chunker = schemas.ChunkingSettings.properties.chunker_config.examples[0] ?? ''
  const embedder = schemas.EmbeddingSettings.properties.embedder_config.examples[0] ?? ''

  expect(Object.fromEntries(parseChunkerConfig(chunker) ?? [])).toEqual({
    version: 'md-header+recursive@v3',
    size: '800',
    overlap: '80',
    min: '100',
    merge: 'fwd,back1.5x,keep',
    breadcrumb: '1',
  })
  expect(Object.fromEntries(parseEmbedderConfig(embedder) ?? [])).toEqual({
    model: 'voyage-4',
    input: 'document',
    dimensions: '1024',
  })
})

test.each([
  [CURRENT.replace('size=800', 'size=1000'), ['size 1000 → 800']],
  [CURRENT.replace('overlap=80', 'overlap=50'), ['overlap 50 → 80']],
  [CURRENT.replace('min=100', 'min=0'), ['min size 0 → 100']],
  [CURRENT.replace('@v3', '@v2'), ['version md-header+recursive@v2 → md-header+recursive@v3']],
  [
    CURRENT.replace('size=800', 'size=1000').replace('breadcrumb=1', 'breadcrumb=0'),
    ['size 1000 → 800', 'heading breadcrumb 0 → 1'],
  ],
  [CURRENT, []],
])('chunker %s -> %j', (stored, expected) => {
  expect(chunkerDiff(stored, CURRENT)).toEqual(expected)
})

test('a part only one side has shows as a dash', () => {
  expect(
    chunkerDiff('md-header+recursive@v2/size=800', 'md-header+recursive@v2/size=800/min=1'),
  ).toEqual(['min size — → 1'])
})

test.each([
  ['voyage-3/document/1024', ['model voyage-3 → voyage-4']],
  ['voyage-4/document/512', ['dimensions 512 → 1024']],
  ['voyage-3/document/512', ['model voyage-3 → voyage-4', 'dimensions 512 → 1024']],
])('embedder %s -> %j', (stored, expected) => {
  expect(embedderDiff(stored, 'voyage-4/document/1024')).toEqual(expected)
})

test.each([
  ['recursive-v1', CURRENT],
  ['md-header+recursive@v3/size', CURRENT],
])('an unreadable config (%s) is null', (stored, current) => {
  expect(chunkerDiff(stored, current)).toBeNull()
  expect(embedderDiff('voyage-4', 'voyage-4/document/1024')).toBeNull()
})

test('the note', () => {
  expect(differsNote(['size 1000 → 800'])).toBe('Now differs: size 1000 → 800')
  expect(differsNote(['size 1000 → 800', 'min size 0 → 100'])).toBe(
    'Now differs: size 1000 → 800, min size 0 → 100',
  )
  expect(differsNote([])).toBeNull()
  expect(differsNote(null)).toBe('Differs from the current settings')
})

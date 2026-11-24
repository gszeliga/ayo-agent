import openapi from '../../../docs/openapi.json'

import {
  backLink,
  backToList,
  chunkLink,
  DOC_ID_PATTERN,
  highlightedChunk,
  highlightSource,
  parseDetailParams,
  toDetailSearch,
} from './params'

const parse = (search: string) => parseDetailParams(new URLSearchParams(search))

test("the id pattern is the API's", () => {
  const parameter = openapi.paths['/admin/documents/{doc_id}'].get.parameters[0]

  expect(parameter?.schema.pattern).toBe(DOC_ID_PATTERN.source)
})

test.each([
  ['', { tab: 'content', view: 'rendered', chunkPage: 1, chunkView: 'raw' }, ''],
  ['view=raw', { tab: 'content', view: 'raw', chunkPage: 1, chunkView: 'raw' }, 'view=raw'],
  [
    'tab=chunks&cpage=3',
    { tab: 'chunks', view: 'rendered', chunkPage: 3, chunkView: 'raw' },
    'tab=chunks&cpage=3',
  ],
  [
    'tab=chunks&cpage=1',
    { tab: 'chunks', view: 'rendered', chunkPage: 1, chunkView: 'raw' },
    'tab=chunks',
  ],
  [
    'tab=vectors&cpage=0&view=x',
    { tab: 'content', view: 'rendered', chunkPage: 1, chunkView: 'raw' },
    '',
  ],
  [
    'tab=chunks&cview=rendered',
    { tab: 'chunks', view: 'rendered', chunkPage: 1, chunkView: 'rendered' },
    'tab=chunks&cview=rendered',
  ],
  [
    'tab=chunks&cview=raw',
    { tab: 'chunks', view: 'rendered', chunkPage: 1, chunkView: 'raw' },
    'tab=chunks',
  ],
  ['cview=rendered', { tab: 'content', view: 'rendered', chunkPage: 1, chunkView: 'rendered' }, ''],
  // Each value only where it applies.
  [
    'tab=chunks&view=raw',
    { tab: 'chunks', view: 'raw', chunkPage: 1, chunkView: 'raw' },
    'tab=chunks',
  ],
])('%j reads as %j and is written as %j', (search, params, written) => {
  expect(parse(search)).toEqual(params)
  expect(toDetailSearch(parse(search)).toString()).toBe(written)
})

test.each([
  [{ listSearch: '?tenant=planta-sur&page=2' }, '/documents?tenant=planta-sur&page=2'],
  [{ listSearch: '?' }, '/documents?'],
  [null, '/documents'],
  [{ listSearch: '//evil.example' }, '/documents'],
  [{ listSearch: 42 }, '/documents'],
])('back from state %j goes to %j', (state, expected) => {
  expect(backToList(state)).toBe(expected)
})

test.each([
  [
    { searchFrom: '?tenant=ayo&k=10', chunkIndex: 3 },
    { to: '/search?tenant=ayo&k=10', target: 'search' },
  ],
  [
    { searchFrom: '?', chunkIndex: 0 },
    { to: '/search', target: 'search' },
  ],
  [{ searchFrom: 'https://evil.example' }, { to: '/documents', target: 'documents' }],
  [
    { chatFrom: '/chat/8d2e4b71-5c3a-4f09-a6e2-000000000001', chunkIndex: 2 },
    { to: '/chat/8d2e4b71-5c3a-4f09-a6e2-000000000001', target: 'chat' },
  ],
  [{ chatFrom: '/chat/new' }, { to: '/documents', target: 'documents' }],
  [{ chatFrom: 'https://evil.example/chat/x' }, { to: '/documents', target: 'documents' }],
  [{ chatFrom: '//evil.example' }, { to: '/documents', target: 'documents' }],
  [{ listSearch: '?tenant=ayo' }, { to: '/documents?tenant=ayo', target: 'documents' }],
  [null, { to: '/documents', target: 'documents' }],
])('back from %j goes to %j', (state, expected) => {
  expect(backLink(state)).toEqual(expected)
})

test.each([
  [{ searchFrom: '?', chunkIndex: 3 }, 3],
  [{ searchFrom: '?', chunkIndex: 0 }, 0],
  [{ chatFrom: '/chat/8d2e4b71-5c3a-4f09-a6e2-000000000001', chunkIndex: 4 }, 4],
  [{ chunkIndex: -1 }, null],
  [{ chunkIndex: 1.5 }, null],
  [{ chunkIndex: '2' }, null],
  [null, null],
])('the chunk outlined for %j is %j', (state, expected) => {
  expect(highlightedChunk(state)).toBe(expected)
})

test.each([
  [{ chatFrom: '/chat/8d2e4b71-5c3a-4f09-a6e2-000000000001', chunkIndex: 1 }, 'chat'],
  [{ searchFrom: '?', chunkIndex: 1 }, 'search'],
  [{ chatFrom: '/elsewhere', chunkIndex: 1 }, 'search'],
])('the outlined chunk opened with %j says %j', (state, expected) => {
  expect(highlightSource(state)).toBe(expected)
})

test('a chunk links to its page of the Chunks tab', () => {
  expect(chunkLink('upload-3f9a1c2b7d4e', 0)).toBe('/documents/upload-3f9a1c2b7d4e?tab=chunks')
  expect(chunkLink('upload-3f9a1c2b7d4e', 19)).toBe('/documents/upload-3f9a1c2b7d4e?tab=chunks')
  expect(chunkLink('upload-3f9a1c2b7d4e', 20)).toBe(
    '/documents/upload-3f9a1c2b7d4e?tab=chunks&cpage=2',
  )
})

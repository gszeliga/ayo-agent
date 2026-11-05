import openapi from '../../../docs/openapi.json'

import { backToList, DOC_ID_PATTERN, parseDetailParams, toDetailSearch } from './params'

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

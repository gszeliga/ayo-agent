import openapi from '../../../docs/openapi.json'

import { TENANT_PATTERN } from '@/documents/listParams'

import { isLong, tenantsSummary } from './format'
import {
  charCount,
  DEFAULT_OPTIONS,
  MAX_TENANTS,
  MAX_TOP_K,
  parseMinSimilarity,
  parseSearchOptions,
  parseTopK,
  QUERY_MAX_CHARS,
  toRequest,
  toSearchParams,
} from './searchParams'

const parse = (search: string) => parseSearchOptions(new URLSearchParams(search))

test('a full URL is read and written back unchanged', () => {
  const search = 'tenant=ayo&tenant=planta-norte&k=10&min=0.5&outdated=1'

  const options = parse(search)

  expect(options).toEqual({
    tenants: ['ayo', 'planta-norte'],
    topK: 10,
    minSimilarity: 0.5,
    includeOutdated: true,
  })
  expect(toSearchParams(options).toString()).toBe(search)
})

test('defaults are left out of the URL', () => {
  expect(parse('')).toEqual(DEFAULT_OPTIONS)
  expect(toSearchParams(DEFAULT_OPTIONS).toString()).toBe('')
  expect(toSearchParams(parse('k=5&outdated=0')).toString()).toBe('')
})

test('tenants are sorted, repeats and invalid ones dropped', () => {
  expect(parse('tenant=planta-sur&tenant=ayo&tenant=ayo&tenant=Planta&tenant=a').tenants).toEqual([
    'ayo',
    'planta-sur',
  ])
})

test('more tenants than the API takes fall back to all', () => {
  const many = Array.from({ length: MAX_TENANTS + 1 }, (_, i) => `tenant=t${String(i)}x`).join('&')

  expect(parse(many).tenants).toEqual([])
  expect(parse(many.split('&').slice(1).join('&')).tenants).toHaveLength(MAX_TENANTS)
})

test.each([
  ['k=0', { topK: 5 }],
  ['k=51', { topK: 5 }],
  ['k=2.5', { topK: 5 }],
  ['k=abc', { topK: 5 }],
  ['k=50', { topK: 50 }],
  ['min=1.5', { minSimilarity: null }],
  ['min=-0.1', { minSimilarity: null }],
  ['min=abc', { minSimilarity: null }],
  ['min=0', { minSimilarity: 0 }],
  ['min=1', { minSimilarity: 1 }],
  ['outdated=true', { includeOutdated: false }],
])('%j gives %j', (search, expected) => {
  expect(parse(search)).toMatchObject(expected)
})

test.each([
  ['1', 1],
  [' 50 ', 50],
  ['0', null],
  ['51', null],
  ['', null],
  ['3.0', null],
])('top k %j is %j', (text, expected) => {
  expect(parseTopK(text)).toBe(expected)
})

test.each([
  ['0.5', 0.5],
  ['0,75', 0.75],
  ['.3', 0.3],
  ['1', 1],
  ['0.1234', 0.1234],
  ['0.12345', null],
  ['1.01', null],
  ['', null],
  ['.', null],
  ['x', null],
])('minimum similarity %j is %j', (text, expected) => {
  expect(parseMinSimilarity(text)).toBe(expected)
})

test('the request: trimmed, debug always on, no filter fields when unset', () => {
  expect(toRequest('  ¿Por dónde empiezo?  ', DEFAULT_OPTIONS)).toEqual({
    query: '¿Por dónde empiezo?',
    top_k: 5,
    include_outdated: false,
    debug: true,
  })
  expect(
    toRequest('x', { tenants: ['ayo'], topK: 3, minSimilarity: 0, includeOutdated: true }),
  ).toEqual({
    query: 'x',
    tenants: ['ayo'],
    top_k: 3,
    min_similarity: 0,
    include_outdated: true,
    debug: true,
  })
})

test('characters are counted as the API counts them', () => {
  expect(charCount('presión 🔧')).toBe(9)
})

test('long chunks: more than three lines or 260 characters', () => {
  expect(isLong('a\nb\nc')).toBe(false)
  expect(isLong('a\nb\nc\nd')).toBe(true)
  expect(isLong('x'.repeat(260))).toBe(false)
  expect(isLong('x'.repeat(261))).toBe(true)
})

test('the tenants summary', () => {
  expect(tenantsSummary([])).toBe('All tenants')
  expect(tenantsSummary(['acme', 'ayo'])).toBe('acme + ayo')
  expect(tenantsSummary(['a1', 'b2', 'c3'])).toBe('3 tenants')
})

test("the limits match the API's", () => {
  const request = openapi.components.schemas.SearchRequest.properties
  const tenants = JSON.stringify(request.tenants)

  expect(request.query.maxLength).toBe(QUERY_MAX_CHARS)
  expect(tenants).toContain(`"maxItems":${String(MAX_TENANTS)}`)
  expect(request.top_k.maximum).toBe(MAX_TOP_K)
  expect(request.top_k.minimum).toBe(1)
  expect(request.top_k.default).toBe(DEFAULT_OPTIONS.topK)
  expect(request.min_similarity.anyOf[0]).toMatchObject({ minimum: 0, maximum: 1 })
  expect(tenants).toContain(JSON.stringify(TENANT_PATTERN.source))
})

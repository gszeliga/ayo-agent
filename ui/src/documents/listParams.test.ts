import openapi from '../../../docs/openapi.json'

import {
  DEFAULT_PARAMS,
  lastPage,
  parseListParams,
  Q_MAX_LENGTH,
  SORT_OPTIONS,
  TENANT_PATTERN,
  toQuery,
  toSearchParams,
} from './listParams'

const parse = (search: string) => parseListParams(new URLSearchParams(search))

test('a full URL is read and written back unchanged', () => {
  const search = 'tenant=planta-norte&q=sellado&sort=title&page=3'

  const params = parse(search)

  expect(params).toEqual({ tenant: 'planta-norte', q: 'sellado', sort: 'title', page: 3 })
  expect(toSearchParams(params).toString()).toBe(search)
})

test('defaults are left out of the URL', () => {
  expect(parse('')).toEqual(DEFAULT_PARAMS)
  expect(toSearchParams(DEFAULT_PARAMS).toString()).toBe('')
  expect(toSearchParams(parse('sort=-updated_at&page=1&q=')).toString()).toBe('')
})

test.each([
  ['tenant=Planta Norte', { tenant: null }],
  ['tenant=a', { tenant: null }],
  ['sort=size', { sort: '-updated_at' }],
  ['page=0', { page: 1 }],
  ['page=-2', { page: 1 }],
  ['page=2.5', { page: 1 }],
  ['page=abc', { page: 1 }],
  [`q=${'x'.repeat(Q_MAX_LENGTH + 1)}`, { q: '' }],
  ['q=%20%20sellado%20', { q: 'sellado' }],
])('%j falls back to %j', (search, expected) => {
  expect(parse(search)).toMatchObject(expected)
})

test('the API query uses offset and the fixed page size', () => {
  expect(toQuery(parse('tenant=planta-sur&page=3'))).toEqual({
    tenant: 'planta-sur',
    sort: '-updated_at',
    limit: 25,
    offset: 50,
  })
})

test('the last page', () => {
  expect([lastPage(0), lastPage(25), lastPage(26)]).toEqual([1, 1, 2])
})

test("the limits match the API's", () => {
  const parameters = openapi.paths['/admin/documents'].get.parameters
  const schema = (name: string) =>
    JSON.stringify(parameters.find((parameter) => parameter.name === name)?.schema)

  expect(schema('tenant')).toContain(JSON.stringify(TENANT_PATTERN.source))
  expect(schema('q')).toContain(`"maxLength":${String(Q_MAX_LENGTH)}`)
  const sorts = parameters.find((parameter) => parameter.name === 'sort')?.schema
  expect(new Set(SORT_OPTIONS.map((option) => option.value))).toEqual(
    new Set((sorts as { enum: string[] }).enum),
  )
})

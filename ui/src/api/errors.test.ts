import { ApiError, describeError } from './errors'

test('parses the API error format', () => {
  const error = ApiError.fromResponse(404, {
    detail: [{ type: 'document_not_found', loc: ['path', 'doc_id'], msg: 'document not found' }],
  })

  expect(error.status).toBe(404)
  expect(error.type).toBe('document_not_found')
  expect(error.message).toBe('document not found')
  expect(error.isNetworkError).toBe(false)
})

test('anything else becomes one generic item with the status', () => {
  const error = ApiError.fromResponse(502, '<html>Bad gateway</html>')

  expect(error.items).toEqual([
    { type: 'unexpected_response', loc: [], msg: 'The API answered HTTP 502' },
  ])
})

test.each([null, {}, { detail: 'nope' }, { detail: [] }, { detail: [{ type: 'x' }] }])(
  'a malformed body %j is generic too',
  (body) => {
    expect(ApiError.fromResponse(500, body).type).toBe('unexpected_response')
  },
)

test('a network failure has no status', () => {
  const cause = new TypeError('fetch failed')
  const error = ApiError.network(cause)

  expect([error.status, error.isNetworkError, error.type, error.cause]).toEqual([
    null,
    true,
    'network_error',
    cause,
  ])
})

test('field errors use the last string of each loc, first message wins', () => {
  const error = ApiError.fromResponse(422, {
    detail: [
      { type: 'string_too_short', loc: ['body', 'title'], msg: 'too short' },
      { type: 'string_pattern_mismatch', loc: ['body', 'doc_ids', 1], msg: 'bad id' },
      { type: 'other', loc: ['body', 'title'], msg: 'ignored' },
      { type: 'embedding_failed', loc: [], msg: 'no field' },
    ],
  })

  expect(error.fieldErrors()).toEqual({ title: 'too short', doc_ids: 'bad id' })
})

describe('describeError', () => {
  const BASE = 'http://api.test'

  test('the API out of reach is worded by the UI, in its language', () => {
    const error = ApiError.network(new TypeError('Failed to fetch'))

    expect(describeError(error, BASE, 'en')).toBe(
      "Can't reach the API at http://api.test. Check the URL and that the API is running.",
    )
    expect(describeError(error, BASE, 'es')).toBe(
      'No se puede conectar con la API en http://api.test. Comprueba la URL y que la API esté en marcha.',
    )
  })

  test('an answer not in the API format names its status, in the UI language', () => {
    const error = ApiError.fromResponse(502, '<html>Bad gateway</html>')

    expect(describeError(error, BASE, 'en')).toBe('The API answered HTTP 502')
    expect(describeError(error, BASE, 'es')).toBe('La API ha respondido HTTP 502')
  })

  test("the API's own message is shown as received, in any language", () => {
    const error = ApiError.fromResponse(500, {
      detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }],
    })

    expect(describeError(error, BASE, 'es')).toBe('internal server error')
    expect(describeError(new Error('boom'), BASE, 'es')).toBe('boom')
  })
})

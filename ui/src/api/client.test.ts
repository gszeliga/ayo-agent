import { http, HttpResponse } from 'msw'

import { server } from '@/test/server'

import { createApiClient, unwrap } from './client'
import { ApiError } from './errors'

const API = 'http://api.test'

test('every request carries the key and the data comes back', async () => {
  let key: string | null = null
  server.use(
    http.get(`${API}/admin/tenants`, ({ request }) => {
      key = request.headers.get('X-API-Key')
      return HttpResponse.json([{ tenant: 'acme', document_count: 4, chunk_count: 57 }])
    }),
  )

  const tenants = await unwrap(createApiClient(API, 'k-1').GET('/admin/tenants'))

  expect(key).toBe('k-1')
  expect(tenants).toEqual([{ tenant: 'acme', document_count: 4, chunk_count: 57 }])
})

test('a 401 calls onUnauthorized and throws the API error', async () => {
  const onUnauthorized = vi.fn()
  server.use(
    http.get(`${API}/admin/tenants`, () =>
      HttpResponse.json(
        { detail: [{ type: 'invalid_api_key', loc: ['header', 'x-api-key'], msg: 'invalid' }] },
        { status: 401 },
      ),
    ),
  )

  const call = unwrap(createApiClient(API, 'bad', { onUnauthorized }).GET('/admin/tenants'))

  await expect(call).rejects.toMatchObject({ status: 401, type: 'invalid_api_key' })
  expect(onUnauthorized).toHaveBeenCalledOnce()
})

test.each([404, 422, 500])('a %i does not call onUnauthorized', async (status) => {
  const onUnauthorized = vi.fn()
  server.use(http.get(`${API}/admin/tenants`, () => HttpResponse.json({}, { status })))

  await expect(
    unwrap(createApiClient(API, 'k', { onUnauthorized }).GET('/admin/tenants')),
  ).rejects.toBeInstanceOf(ApiError)
  expect(onUnauthorized).not.toHaveBeenCalled()
})

test('a network failure is an ApiError without status', async () => {
  server.use(http.get(`${API}/admin/tenants`, () => HttpResponse.error()))

  const error: unknown = await unwrap(createApiClient(API, 'k').GET('/admin/tenants')).catch(
    (err: unknown) => err,
  )

  expect(error).toBeInstanceOf(ApiError)
  expect((error as ApiError).isNetworkError).toBe(true)
})

test('a 204 unwraps to undefined', async () => {
  server.use(
    http.delete(`${API}/admin/documents/:docId`, () => new HttpResponse(null, { status: 204 })),
  )

  const call = unwrap(
    createApiClient(API, 'k').DELETE('/admin/documents/{doc_id}', {
      params: { path: { doc_id: 'upload-1890b5dc5335' } },
    }),
  )

  await expect(call).resolves.toBeUndefined()
})

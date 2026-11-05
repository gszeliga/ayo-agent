import { http, HttpResponse } from 'msw'

import { server } from './server'

const API = 'http://api.test'

test('a handler answers a request', async () => {
  server.use(http.get(`${API}/health`, () => HttpResponse.json({ status: 'ok' })))

  const response = await fetch(`${API}/health`)

  expect(await response.json()).toEqual({ status: 'ok' })
})

test('a request no handler answers fails, refused by MSW', async () => {
  const error: unknown = await fetch(`${API}/admin/tenants`).catch((err: unknown) => err)

  expect(error).toBeInstanceOf(TypeError)
  // MSW's refusal, not a network failure that would pass the test for the wrong reason.
  expect(String((error as TypeError).cause)).toMatch(/\[MSW\].*"error" strategy/)
})

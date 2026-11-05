import { isServerReachable, unreachableMessage } from './reachability'

test('a no-cors request to /health that succeeds means the server answers', async () => {
  const fetchFn = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 200 }))

  await expect(isServerReachable('http://api.test', fetchFn)).resolves.toBe(true)
  const [url, init] = fetchFn.mock.calls[0] ?? []
  expect(url).toBe('http://api.test/health')
  expect(init).toMatchObject({ mode: 'no-cors', cache: 'no-store' })
  expect(init?.signal).toBeInstanceOf(AbortSignal)
})

test('any status counts as answering (an opaque response hides it anyway)', async () => {
  const fetchFn = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 503 }))

  await expect(isServerReachable('http://api.test', fetchFn)).resolves.toBe(true)
})

test('a failed request (down, wrong host, timeout) means it does not', async () => {
  const fetchFn = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('fetch failed'))

  await expect(isServerReachable('http://api.test', fetchFn)).resolves.toBe(false)
})

test('the messages name the fix', () => {
  expect(unreachableMessage('http://api.test', true, 'http://localhost:5173')).toBe(
    'The API at http://api.test answers, but refuses requests from this page. Add' +
      ' http://localhost:5173 to CORS_ALLOWED_ORIGINS and restart the API.',
  )
  expect(unreachableMessage('http://api.test', false, 'http://localhost:5173')).toBe(
    "Can't reach the API at http://api.test. Check the URL and that the API is running.",
  )
})

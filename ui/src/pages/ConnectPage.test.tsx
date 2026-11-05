import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { loadConnection } from '@/connection/storage'
import { API, KEY, renderApp } from '@/test/render'
import { server } from '@/test/server'

function tenantsAnswer(status: number) {
  return http.get(`${API}/admin/tenants`, ({ request }) =>
    status === 200 && request.headers.get('X-API-Key') === KEY
      ? HttpResponse.json([])
      : HttpResponse.json(
          { detail: [{ type: 'invalid_api_key', loc: ['header', 'x-api-key'], msg: 'invalid' }] },
          { status: 401 },
        ),
  )
}

async function fillAndConnect(
  user: ReturnType<typeof renderApp>['user'],
  { url = API, key = KEY }: { url?: string; key?: string } = {},
) {
  const address = screen.getByLabelText('API address')
  await user.clear(address)
  if (url) await user.type(address, url)
  if (key) await user.type(screen.getByLabelText('Admin key'), key)
  await user.click(screen.getByRole('button', { name: 'Connect' }))
}

test('the address defaults to the page origin outside a dev build', () => {
  renderApp('/connect')

  expect(screen.getByLabelText('API address')).toHaveValue(window.location.origin)
})

test('a valid key is kept for the tab and opens the requested page', async () => {
  server.use(tenantsAnswer(200))
  const { user } = renderApp('/connect?next=%2Fsettings')

  await fillAndConnect(user, { url: `${API}/` })

  expect(await screen.findByRole('heading', { name: 'Indexing settings' })).toBeInTheDocument()
  expect(loadConnection()).toEqual({ baseUrl: API, apiKey: KEY })
})

test('a rejected key is reported next to the key field', async () => {
  server.use(tenantsAnswer(401))
  const { user } = renderApp('/connect')

  await fillAndConnect(user, { key: 'wrong' })

  const keyField = screen.getByLabelText('Admin key')
  expect(await screen.findByText('Key rejected.')).toBeInTheDocument()
  expect(keyField).toHaveAttribute('aria-invalid', 'true')
  expect(keyField).toHaveAccessibleDescription('Key rejected.')
  expect(loadConnection()).toBeNull()
})

test('an unreachable API names the URL and CORS', async () => {
  server.use(http.get(`${API}/admin/tenants`, () => HttpResponse.error()))
  const { user } = renderApp('/connect')

  await fillAndConnect(user)

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(`Can't reach the API at ${API}`)
  expect(alert).toHaveTextContent(`CORS_ALLOWED_ORIGINS includes ${window.location.origin}`)
})

test('another error shows its message', async () => {
  server.use(
    http.get(`${API}/admin/tenants`, () =>
      HttpResponse.json(
        { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
        { status: 500 },
      ),
    ),
  )
  const { user } = renderApp('/connect')

  await fillAndConnect(user)

  expect(await screen.findByRole('alert')).toHaveTextContent('internal server error')
})

test('fields are checked before calling the API', async () => {
  // No handler: a request would fail the test.
  const { user } = renderApp('/connect')

  await fillAndConnect(user, { url: 'https://host/admin', key: '' })

  expect(screen.getByText(/without a path/)).toBeInTheDocument()
  expect(screen.getByText('Enter the admin key.')).toBeInTheDocument()
})

test.each(['//evil.example', 'https://evil.example', '/connect', 'documents'])(
  'an unsafe next (%j) falls back to the documents',
  async (next) => {
    server.use(tenantsAnswer(200))
    const { user } = renderApp(`/connect?next=${encodeURIComponent(next)}`)

    await fillAndConnect(user)

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents$/)
  },
)

test('the key can be shown and hidden', async () => {
  const { user } = renderApp('/connect')
  const keyField = screen.getByLabelText('Admin key')

  expect(keyField).toHaveAttribute('type', 'password')
  await user.click(screen.getByRole('button', { name: 'Show key' }))
  expect(keyField).toHaveAttribute('type', 'text')
})

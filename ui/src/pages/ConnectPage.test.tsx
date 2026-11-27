import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { loadConnection } from '@/connection/storage'
import { LANGUAGE_KEY } from '@/lib/language'
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
  await user.click(screen.getByRole('button', { name: 'Change the API address' }))
  const address = screen.getByLabelText('API address')
  await user.clear(address)
  if (url) await user.type(address, url)
  if (key) await user.type(screen.getByLabelText('Admin key'), key)
  await user.click(screen.getByRole('button', { name: 'Connect' }))
}

test('the address defaults to the page origin, shown as text behind Change', async () => {
  const { user } = renderApp('/connect')

  expect(screen.queryByRole('textbox', { name: 'API address' })).not.toBeInTheDocument()
  expect(screen.getByText(window.location.origin)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Change the API address' }))

  const address = screen.getByRole('textbox', { name: 'API address' })
  expect(address).toHaveValue(window.location.origin)
  expect(address).toHaveFocus()
  expect(screen.queryByRole('button', { name: 'Change the API address' })).not.toBeInTheDocument()
})

test('connecting without opening the address uses the default', async () => {
  server.use(
    http.get(`${window.location.origin}/admin/tenants`, ({ request }) =>
      request.headers.get('X-API-Key') === KEY
        ? HttpResponse.json([])
        : HttpResponse.json({ detail: [] }, { status: 401 }),
    ),
  )
  const { user } = renderApp('/connect?next=%2Fsettings')

  await user.type(screen.getByLabelText('Admin key'), KEY)
  await user.click(screen.getByRole('button', { name: 'Connect' }))

  expect(await screen.findByRole('heading', { name: 'Indexing settings' })).toBeInTheDocument()
  expect(loadConnection()).toEqual({ baseUrl: window.location.origin, apiKey: KEY })
})

test('an address that does not answer opens the field', async () => {
  const origin = window.location.origin
  server.use(
    http.get(`${origin}/admin/tenants`, () => HttpResponse.error()),
    http.get(`${origin}/health`, () => HttpResponse.error()),
  )
  const { user } = renderApp('/connect')

  await user.type(screen.getByLabelText('Admin key'), KEY)
  await user.click(screen.getByRole('button', { name: 'Connect' }))

  expect(await screen.findByRole('alert')).toBeInTheDocument()
  const address = screen.getByRole('textbox', { name: 'API address' })
  expect(address).toHaveValue(origin)
  expect(address).toHaveFocus()
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

test('an API that answers but refuses this origin is reported as a CORS problem', async () => {
  // How a CORS refusal looks to the page: the call fails, a no-cors request succeeds.
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.error()),
    http.get(`${API}/health`, () => HttpResponse.json({ status: 'ok' })),
  )
  const { user } = renderApp('/connect')

  await fillAndConnect(user)

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(`The API at ${API} answers, but refuses requests`)
  expect(alert).toHaveTextContent(`Add ${window.location.origin} to CORS_ALLOWED_ORIGINS`)
})

test('an API that does not answer at all is reported as unreachable', async () => {
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.error()),
    http.get(`${API}/health`, () => HttpResponse.error()),
  )
  const { user } = renderApp('/connect')

  await fillAndConnect(user)

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(`Can't reach the API at ${API}`)
  expect(alert).not.toHaveTextContent('CORS')
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

describe('in Spanish', () => {
  async function fillAndConnectEs(
    user: ReturnType<typeof renderApp>['user'],
    { url = API, key = KEY }: { url?: string; key?: string } = {},
  ) {
    await user.click(screen.getByRole('button', { name: 'Cambiar la dirección de la API' }))
    const address = screen.getByLabelText('Dirección de la API')
    await user.clear(address)
    if (url) await user.type(address, url)
    if (key) await user.type(screen.getByLabelText('Clave de administración'), key)
    await user.click(screen.getByRole('button', { name: 'Conectar' }))
  }

  test('the screen and its field checks are Spanish, and reword on a switch', async () => {
    const { user } = renderApp('/connect', { language: 'es' })

    expect(screen.getByRole('heading', { name: 'Conéctate a la API de AYO' })).toBeInTheDocument()
    expect(document.title).toBe('Conectar · AYO Admin')
    expect(screen.getByRole('button', { name: 'Mostrar clave' })).toBeInTheDocument()
    await fillAndConnectEs(user, { url: 'https://host/admin', key: '' })
    expect(screen.getByText(/sin ruta/)).toBeInTheDocument()
    expect(screen.getByText('Escribe la clave de administración.')).toBeInTheDocument()

    // A message already shown follows the language.
    await user.click(screen.getByRole('button', { name: 'Idioma: Español' }))
    await user.click(await screen.findByRole('menuitemradio', { name: 'English' }))
    expect(screen.getByText('Enter the admin key.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Connect to the AYO API' })).toBeInTheDocument()
  })

  test('a rejected key is reported in Spanish', async () => {
    server.use(tenantsAnswer(401))
    const { user } = renderApp('/connect', { language: 'es' })

    await fillAndConnectEs(user, { key: 'wrong' })

    expect(await screen.findByText('Clave rechazada.')).toBeInTheDocument()
    expect(screen.getByLabelText('Clave de administración')).toHaveAccessibleDescription(
      'Clave rechazada.',
    )
  })

  test('a CORS refusal is explained in Spanish', async () => {
    server.use(
      http.get(`${API}/admin/tenants`, () => HttpResponse.error()),
      http.get(`${API}/health`, () => HttpResponse.json({ status: 'ok' })),
    )
    const { user } = renderApp('/connect', { language: 'es' })

    await fillAndConnectEs(user)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(`La API en ${API} responde, pero rechaza las peticiones`)
    expect(alert).toHaveTextContent(`Añade ${window.location.origin} a CORS_ALLOWED_ORIGINS`)
  })
})

test('a language chosen on the connect screen is kept once connected', async () => {
  server.use(tenantsAnswer(200))
  const { user } = renderApp('/connect?next=%2Fsettings')

  await user.click(screen.getByRole('button', { name: 'Language: system' }))
  await user.click(await screen.findByRole('menuitemradio', { name: 'Español' }))
  expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('es')
  await user.click(screen.getByRole('button', { name: 'Cambiar la dirección de la API' }))
  const address = screen.getByLabelText('Dirección de la API')
  await user.clear(address)
  await user.type(address, API)
  await user.type(screen.getByLabelText('Clave de administración'), KEY)
  await user.click(screen.getByRole('button', { name: 'Conectar' }))

  expect(
    await screen.findByRole('button', { name: /^Conexión y preferencias:/ }),
  ).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: 'Principal' })).toHaveTextContent('Búsqueda')
})

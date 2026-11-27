import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { makeHealth } from '@/test/fixtures/services'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

const pill = () => screen.getByRole('button', { name: /^(Service status|Estado del servicio)/ })

const down = { status: 'down' as const, error: 'unreachable' }

test.each([
  [{}, 'All systems ok', 'Service status: database up, embeddings up'],
  [{ embeddings: down }, 'Embeddings down', 'Service status: database up, embeddings down'],
  [{ database: down }, 'Database down', 'Service status: database down, embeddings up'],
  [
    { database: down, embeddings: down },
    'Database and embeddings down',
    'Service status: database down, embeddings down',
  ],
])('health %j shows %j', async (overrides, text, name) => {
  server.use(http.get(`${API}/admin/health`, () => HttpResponse.json(makeHealth(overrides))))
  const { user } = renderApp('/documents', { connected: true })

  expect(await screen.findByText(text)).toBeInTheDocument()
  expect(pill()).toHaveTextContent(text)
  expect(pill()).toHaveAccessibleName(name)

  await user.click(pill())
  expect(await screen.findByRole('region', { name: 'Database service' })).toBeInTheDocument()
})

test('while the first answer is on its way it says Checking', () => {
  server.use(http.get(`${API}/admin/health`, () => new Promise<Response>(() => undefined)))
  renderApp('/documents', { connected: true })

  expect(pill()).toHaveTextContent('Checking…')
  expect(pill()).toHaveAccessibleName(
    'Service status: database status unknown, embeddings status unknown',
  )
})

test('a failed check says the status is unknown', async () => {
  server.use(http.get(`${API}/admin/health`, () => new HttpResponse(null, { status: 500 })))
  renderApp('/documents', { connected: true })

  expect(await screen.findByText('Status unknown')).toBeInTheDocument()
  expect(pill()).toHaveAccessibleName(
    'Service status: database status unknown, embeddings status unknown',
  )
})

test('the pill speaks Spanish', async () => {
  server.use(
    http.get(`${API}/admin/health`, () =>
      HttpResponse.json(makeHealth({ database: down, embeddings: down })),
    ),
  )
  renderApp('/documents', { connected: true, language: 'es' })

  expect(await screen.findByText('Base de datos y embeddings sin servicio')).toBeInTheDocument()
  expect(pill()).toHaveAccessibleName(
    'Estado del servicio: base de datos sin servicio, embeddings sin servicio',
  )
})

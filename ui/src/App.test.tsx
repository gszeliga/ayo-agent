import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { useState } from 'react'
import { Route, Routes } from 'react-router'

import { unwrap } from '@/api/client'
import { App } from '@/App'
import { useApiClient } from '@/connection/context'
import { KEY_REJECTED } from '@/connection/ConnectionProvider'
import { RequireConnection } from '@/connection/RequireConnection'
import { loadConnection } from '@/connection/storage'
import { ConnectPage } from '@/pages/ConnectPage'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

test('the app starts on the connect screen', () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: 'Connect to the AYO API' })).toBeInTheDocument()
})

test('a page needs a connection and comes back after connecting', () => {
  renderApp('/documents/upload-1890b5dc5335?tab=chunks')

  expect(screen.getByRole('heading', { name: 'Connect to the AYO API' })).toBeInTheDocument()
  expect(screen.getByTestId('location')).toHaveTextContent(
    '/connect?next=%2Fdocuments%2Fupload-1890b5dc5335%3Ftab%3Dchunks',
  )
})

test('connected, the shell shows the host, the nav and the page', () => {
  renderApp('/', { connected: true })

  expect(screen.getByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  expect(screen.getByText('api.test')).toBeInTheDocument()
  const nav = screen.getByRole('navigation', { name: 'Main' })
  expect(nav).toHaveTextContent('DocumentsIndexing settings')
  expect(screen.getByRole('link', { name: 'Documents' })).toHaveAttribute('aria-current', 'page')
})

test('disconnect forgets the key and returns to the connect screen', async () => {
  const { user } = renderApp('/settings', { connected: true })

  await user.click(screen.getByRole('button', { name: 'Disconnect' }))

  expect(screen.getByRole('heading', { name: 'Connect to the AYO API' })).toBeInTheDocument()
  expect(loadConnection()).toBeNull()
  expect(screen.queryByText(KEY_REJECTED)).not.toBeInTheDocument()
})

function Probe() {
  const client = useApiClient()
  const [failed, setFailed] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        unwrap(client.GET('/admin/tenants')).catch(() => {
          setFailed(true)
        })
      }}
    >
      {failed ? 'failed' : 'load'}
    </button>
  )
}

test('a 401 on any request returns to the connect screen with a notice', async () => {
  server.use(
    http.get(`${API}/admin/tenants`, () =>
      HttpResponse.json(
        { detail: [{ type: 'invalid_api_key', loc: ['header', 'x-api-key'], msg: 'invalid' }] },
        { status: 401 },
      ),
    ),
  )
  const routes = (
    <Routes>
      <Route path="/connect" element={<ConnectPage />} />
      <Route element={<RequireConnection />}>
        <Route path="/probe" element={<Probe />} />
      </Route>
    </Routes>
  )
  const { user } = renderApp('/probe', { connected: true, routes })

  await user.click(screen.getByRole('button', { name: 'load' }))

  expect(await screen.findByText(KEY_REJECTED)).toBeInTheDocument()
  expect(screen.getByTestId('location')).toHaveTextContent('/connect?next=%2Fprobe')
  expect(loadConnection()).toBeNull()
})

test('the internal-use banner stays dismissed', async () => {
  const { user, unmount } = renderApp('/documents', { connected: true })
  expect(screen.getByRole('note')).toHaveTextContent('Internal use only')

  await user.click(screen.getByRole('button', { name: 'Dismiss' }))
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
  unmount()

  renderApp('/documents', { connected: true })
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

test('an unknown path shows the not-found page', () => {
  renderApp('/nothing/here', { connected: true })

  expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
})

test('an already connected visit to /connect goes on to the app', () => {
  renderApp('/connect?next=%2Fsettings', { connected: true })

  expect(screen.getByRole('heading', { name: 'Indexing settings' })).toBeInTheDocument()
})

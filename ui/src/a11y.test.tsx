import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { a11yViolations } from '@/test/axe'
import { DOCUMENTS, TENANTS } from '@/test/fixtures/documents'
import { PROCEDURE_MD } from '@/test/fixtures/markdown'
import { makeSearchResponse, QUESTION } from '@/test/fixtures/search'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

const DOC = DOCUMENTS[0]!

beforeEach(() => {
  server.use(
    http.get(`${API}/admin/documents`, () =>
      HttpResponse.json({ items: DOCUMENTS, total: 3, limit: 25, offset: 0 }),
    ),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/documents/:docId`, () => HttpResponse.json(DOC)),
    http.get(`${API}/admin/documents/:docId/content`, () => new HttpResponse(PROCEDURE_MD)),
  )
})

test('connect', async () => {
  renderApp('/connect')
  await screen.findByRole('heading', { name: 'Connect to the AYO API' })

  expect(await a11yViolations()).toEqual([])
})

test('documents list', async () => {
  renderApp('/documents', { connected: true })
  await screen.findByRole('table', { name: 'Documents' })

  expect(await a11yViolations()).toEqual([])
})

test('document detail, rendered content', async () => {
  renderApp(`/documents/${DOC.doc_id}`, { connected: true })
  await screen.findByRole('heading', { name: 'PRO-014 Control de sellado', level: 1 })
  await screen.findByRole('table')

  expect(await a11yViolations()).toEqual([])
})

test('settings', async () => {
  renderApp('/settings', { connected: true })
  await screen.findByRole('region', { name: 'Chunking' })

  expect(await a11yViolations()).toEqual([])
})

test('upload dialog', async () => {
  const { user } = renderApp('/documents', { connected: true })
  await screen.findByRole('table', { name: 'Documents' })
  await user.click(screen.getByRole('button', { name: 'Upload' }))
  await screen.findByRole('dialog', { name: 'Upload a document' })

  expect(await a11yViolations()).toEqual([])
})

test('delete dialog', async () => {
  const { user } = renderApp(`/documents/${DOC.doc_id}`, { connected: true })
  await user.click(await screen.findByRole('button', { name: 'Delete' }))
  await screen.findByRole('alertdialog')

  expect(await a11yViolations()).toEqual([])
})

test('search, before a search', async () => {
  renderApp('/search', { connected: true })
  await screen.findByText('Results appear here')

  expect(await a11yViolations()).toEqual([])
})

test('search, with results and the skipped banner', async () => {
  server.use(
    http.post(`${API}/admin/search`, () =>
      HttpResponse.json(makeSearchResponse({ skipped: { embedder_mismatch: 2 } })),
    ),
  )
  const { user } = renderApp('/search', { connected: true })
  await user.type(await screen.findByLabelText('Question'), QUESTION)
  await user.keyboard('{Enter}')
  await screen.findByRole('list', { name: 'Results' })
  await user.click(screen.getByRole('button', { name: 'Details' }))

  expect(await a11yViolations()).toEqual([])
})

test('search, failed', async () => {
  server.use(
    http.post(`${API}/admin/search`, () =>
      HttpResponse.json(
        { detail: [{ type: 'embedding_failed', loc: [], msg: 'embedding provider failed' }] },
        { status: 502 },
      ),
    ),
  )
  const { user } = renderApp('/search', { connected: true })
  await user.type(await screen.findByLabelText('Question'), QUESTION)
  await user.keyboard('{Enter}')
  await screen.findByRole('alert')

  expect(await a11yViolations()).toEqual([])
})

test('search, tenant picker open', async () => {
  const { user } = renderApp('/search', { connected: true })
  await user.click(await screen.findByRole('button', { name: /Tenants/ }))
  await screen.findByRole('checkbox', { name: /planta-norte/ })

  expect(await a11yViolations()).toEqual([])
})

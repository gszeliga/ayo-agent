import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { a11yViolations } from '@/test/axe'
import { DOCUMENTS, TENANTS } from '@/test/fixtures/documents'
import { PROCEDURE_MD } from '@/test/fixtures/markdown'
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

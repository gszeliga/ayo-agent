import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { resources } from '@/i18n/resources'
import { LANGUAGES, type Language } from '@/lib/language'
import { a11yViolations } from '@/test/axe'
import { serveChat, servedCase } from '@/test/chatApi'
import { CASES } from '@/test/fixtures/cases'
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

// Every screen in every language: the names below come from the language's own catalogs,
// so a screen is found by what it says in that language.
describe.each(LANGUAGES)('in %s', (language: Language) => {
  const c = resources[language]
  const render = (path: string, connected = true) => renderApp(path, { connected, language })

  test('connect', async () => {
    render('/connect', false)
    await screen.findByRole('heading', { name: c.connect.title })

    expect(await a11yViolations()).toEqual([])
  })

  test('documents list', async () => {
    render('/documents')
    await screen.findByRole('table', { name: c.documents.table.label })

    expect(await a11yViolations()).toEqual([])
  })

  test('document detail, rendered content', async () => {
    render(`/documents/${DOC.doc_id}`)
    await screen.findByRole('heading', { name: 'PRO-014 Control de sellado', level: 1 })
    await screen.findByRole('table')

    expect(await a11yViolations()).toEqual([])
  })

  test('settings', async () => {
    render('/settings')
    await screen.findByRole('region', { name: c.settings.card.chunking })

    expect(await a11yViolations()).toEqual([])
  })

  test('upload dialog', async () => {
    const { user } = render('/documents')
    await screen.findByRole('table', { name: c.documents.table.label })
    await user.click(screen.getByRole('button', { name: c.documents.upload }))
    await screen.findByRole('dialog', { name: c.upload.uploadTitle })

    expect(await a11yViolations()).toEqual([])
  })

  test('delete dialog', async () => {
    const { user } = render(`/documents/${DOC.doc_id}`)
    await user.click(await screen.findByRole('button', { name: c.document.delete.button }))
    await screen.findByRole('alertdialog')

    expect(await a11yViolations()).toEqual([])
  })

  test('search, before a search', async () => {
    render('/search')
    await screen.findByText(c.search.empty.introTitle)

    expect(await a11yViolations()).toEqual([])
  })

  test('search, with results and the skipped banner', async () => {
    server.use(
      http.post(`${API}/admin/search`, () =>
        HttpResponse.json(makeSearchResponse({ skipped: { embedder_mismatch: 2 } })),
      ),
    )
    const { user } = render('/search')
    await user.type(await screen.findByLabelText(c.search.form.question), QUESTION)
    await user.keyboard('{Enter}')
    await screen.findByRole('list', { name: c.search.form.results })
    await user.click(screen.getByRole('button', { name: c.search.summary.details }))

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
    const { user } = render('/search')
    await user.type(await screen.findByLabelText(c.search.form.question), QUESTION)
    await user.keyboard('{Enter}')
    await screen.findByRole('alert')

    expect(await a11yViolations()).toEqual([])
  })

  test('search, tenant picker open', async () => {
    const { user } = render('/search')
    await user.click(
      await screen.findByRole('button', { name: new RegExp(c.search.tenants.label) }),
    )
    await screen.findByRole('checkbox', { name: /planta-norte/ })

    expect(await a11yViolations()).toEqual([])
  })

  test('test chat: a case, then its Export and Delete dialogs', async () => {
    const cases = CASES.map((item) => servedCase(item))
    serveChat(cases)
    const { user } = render(`/chat/${cases[0]?.detail.case_id ?? ''}`)
    await screen.findByRole('log', { name: c.chat.conversation })
    // "Turn 3" / "Turno 3": the label with its number as a pattern.
    const turnName = new RegExp(`^${c.chat.turn.label.replace('{{n}}', '\\d+')}$`)
    await screen.findAllByRole('listitem', { name: turnName })
    expect(await a11yViolations()).toEqual([])

    await user.click(screen.getByRole('button', { name: c.chat.header.export }))
    const exporting = await screen.findByRole('dialog', { name: c.chat.exportDialog.title })
    await screen.findByLabelText(c.chat.exportDialog.preview)
    expect(await a11yViolations(exporting)).toEqual([])
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })

    await user.click(screen.getByRole('button', { name: c.chat.header.delete }))
    expect(await a11yViolations(await screen.findByRole('alertdialog'))).toEqual([])
    // axe three times over a full case: like ChatSession's, slow when every file runs.
  }, 15_000)
})

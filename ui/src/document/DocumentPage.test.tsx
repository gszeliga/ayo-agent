import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { DOCUMENTS, makeDocument, TENANTS } from '@/test/fixtures/documents'
import { PROCEDURE_MD } from '@/test/fixtures/markdown'
import { makeSettings } from '@/test/fixtures/services'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

type Chunk = components['schemas']['Chunk']

const DOC = makeDocument({
  title: 'PRO-014 Control de sellado',
  chunk_count: 45,
  content_hash: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
  embed_signature: '17047d562b7e9a3c0f5d8b1e4a7c2f6d9b0e3a8c5f1d4b7e2a9c6f0d3b8e5a1c',
})
const BASE = `${API}/admin/documents/${DOC.doc_id}`
// A function: a response's body can be read only once, so each request needs its own.
const notFound = () =>
  HttpResponse.json(
    {
      detail: [{ type: 'document_not_found', loc: ['path', 'doc_id'], msg: 'document not found' }],
    },
    { status: 404 },
  )

function makeChunks(total: number, vectors: boolean): Chunk[] {
  return Array.from({ length: total }, (_, i) => ({
    chunk_index: i,
    heading: `PRO-014 Control de sellado > ${String(i + 1)}. Paso`,
    chunk_text: `Paso ${String(i + 1)}: comprobar la presión de la junta.\nAnotar el valor.`,
    char_count: 60 + i,
    embedding: vectors ? Array.from({ length: 1024 }, (_, d) => (d % 7) / 10) : null,
  }))
}

/** The document's three endpoints; records the chunk queries and whether content was asked. */
function serve() {
  const calls = { content: 0, chunks: [] as URLSearchParams[] }
  server.use(
    http.get(BASE, () => HttpResponse.json(DOC)),
    http.get(`${BASE}/content`, () => {
      calls.content += 1
      return new HttpResponse(PROCEDURE_MD, {
        headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
      })
    }),
    http.get(`${BASE}/chunks`, ({ request }) => {
      const query = new URL(request.url).searchParams
      calls.chunks.push(query)
      const all = makeChunks(45, query.get('include_embedding') === 'true')
      const offset = Number(query.get('offset'))
      const limit = Number(query.get('limit'))
      return HttpResponse.json({
        items: all.slice(offset, offset + limit),
        total: all.length,
        limit,
        offset,
      })
    }),
  )
  return calls
}

const location = () => screen.getByTestId('location').textContent
const facts = () => screen.getByRole('complementary', { name: 'Facts' })
/** The page's "← Documents" link (the shell's nav has a "Documents" link too). */
const backLink = async () =>
  within(await screen.findByRole('main')).findByRole('link', { name: 'Documents' })

test('header and facts show the document', async () => {
  serve()
  renderApp(`/documents/${DOC.doc_id}`, { connected: true })

  expect(
    await screen.findByRole('heading', { name: 'PRO-014 Control de sellado' }),
  ).toBeInTheDocument()
  expect(screen.getByText('Indexed')).toBeInTheDocument()
  expect(screen.getByText(DOC.doc_id)).toBeInTheDocument()
  expect(window.document.title).toBe('PRO-014 Control de sellado · AYO Admin')
  const panel = facts()
  expect(panel).toHaveTextContent('Source keypro-014-control-sellado.md')
  expect(panel).toHaveTextContent('Chunks45')
  expect(panel).toHaveTextContent('Size4.2 KB')
  expect(panel).toHaveTextContent('Content hash9f86d081884c…')
  expect(panel).toHaveTextContent('Embedder configvoyage-4/document/1024')
})

test('missing values read "not recorded"', async () => {
  const old = makeDocument({
    chunker_config: null,
    embedder_config: null,
    size_bytes: null,
    chunked_at: null,
  })
  server.use(
    http.get(`${API}/admin/documents/${old.doc_id}`, () => HttpResponse.json(old)),
    http.get(`${API}/admin/documents/${old.doc_id}/content`, () => new HttpResponse('# Antiguo')),
  )
  renderApp(`/documents/${old.doc_id}`, { connected: true })

  await screen.findByRole('complementary', { name: 'Facts' })
  expect(within(facts()).getAllByText('not recorded')).toHaveLength(4)
  expect(within(facts()).queryByText(/differs/i)).not.toBeInTheDocument()
})

test('hashes copy their full value', async () => {
  serve()
  const { user } = renderApp(`/documents/${DOC.doc_id}`, { connected: true })
  await screen.findByRole('complementary', { name: 'Facts' })

  await user.click(screen.getByRole('button', { name: 'Copy embed signature' }))

  expect(await navigator.clipboard.readText()).toBe(DOC.embed_signature)
})

test('the header shows at once from the list, before the detail answers', async () => {
  server.use(
    http.get(`${API}/admin/documents`, () =>
      HttpResponse.json({ items: DOCUMENTS, total: 3, limit: 25, offset: 0 }),
    ),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/documents/:docId`, async () => {
      await delay('infinite')
      return HttpResponse.json({})
    }),
    http.get(`${API}/admin/documents/:docId/content`, () => new HttpResponse('# Hola')),
  )
  const { user } = renderApp('/documents?tenant=planta-norte', { connected: true })

  await user.click(
    await screen.findByRole('link', { name: 'Manual de mantenimiento de la caldera B2' }),
  )

  expect(
    screen.getByRole('heading', { name: 'Manual de mantenimiento de la caldera B2' }),
  ).toBeInTheDocument()
})

test('back returns to the list as it was left', async () => {
  server.use(
    http.get(`${API}/admin/documents`, () =>
      HttpResponse.json({ items: DOCUMENTS, total: 3, limit: 25, offset: 0 }),
    ),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/documents/:docId`, ({ params }) =>
      HttpResponse.json(DOCUMENTS.find((doc) => doc.doc_id === params.docId)),
    ),
    http.get(`${API}/admin/documents/:docId/content`, () => new HttpResponse('# Hola')),
  )
  const { user } = renderApp('/documents?q=sellado&sort=title', { connected: true })
  await user.click(await screen.findByRole('link', { name: 'PRO-014 Control de sellado' }))
  await user.click(await screen.findByRole('button', { name: 'Raw' }))

  await user.click(await backLink())

  expect(location()).toBe('/documents?q=sellado&sort=title')
})

test('opened from a link, back goes to the plain list', async () => {
  serve()
  renderApp(`/documents/${DOC.doc_id}`, { connected: true })

  expect(await backLink()).toHaveAttribute('href', '/documents')
})

test('the content renders, safely', async () => {
  serve()
  const { container } = renderApp(`/documents/${DOC.doc_id}`, { connected: true })

  const table = await screen.findByRole('table')
  expect(table).toHaveTextContent('Selladora A3,8 bar')
  expect(screen.getByText('Image not shown: Esquema de la junta')).toBeInTheDocument()
  expect(container.querySelector('script, img')).toBeNull()
})

test('raw shows the exact Markdown, in the URL, and copies it', async () => {
  serve()
  const { user } = renderApp(`/documents/${DOC.doc_id}`, { connected: true })

  await user.click(await screen.findByRole('button', { name: 'Raw' }))

  expect(location()).toBe(`/documents/${DOC.doc_id}?view=raw`)
  expect(await screen.findByText(/^# PRO-014 Control de sellado/)).toHaveTextContent(
    '| Selladora A | 3,8 bar | 4,4 bar |',
  )
  await user.click(screen.getByRole('button', { name: 'Copy Markdown' }))
  expect(await navigator.clipboard.readText()).toBe(PROCEDURE_MD)
})

test('the chunks are not fetched until their tab opens', async () => {
  const calls = serve()
  const { user } = renderApp(`/documents/${DOC.doc_id}`, { connected: true })
  await screen.findByRole('table')
  expect(calls.chunks).toHaveLength(0)

  await user.click(screen.getByRole('tab', { name: 'Chunks' }))

  expect(location()).toBe(`/documents/${DOC.doc_id}?tab=chunks`)
  const first = await screen.findByRole('article', { name: 'Chunk 0' })
  expect(first).toHaveTextContent('#0')
  expect(first).toHaveTextContent('PRO-014 Control de sellado > 1. Paso')
  expect(first).toHaveTextContent('60 chars')
  expect(within(first).getByText(/Paso 1: comprobar/).textContent).toContain('\nAnotar el valor.')
  expect(screen.getAllByRole('article')).toHaveLength(20)
  expect(screen.getByText('1–20 of 45')).toBeInTheDocument()
  expect(Object.fromEntries(calls.chunks[0]!)).toEqual({
    limit: '20',
    offset: '0',
    include_embedding: 'false',
  })
})

test('chunk pages move through the URL', async () => {
  const calls = serve()
  const { user } = renderApp(`/documents/${DOC.doc_id}?tab=chunks&cpage=2`, { connected: true })

  expect(await screen.findByText('21–40 of 45')).toBeInTheDocument()
  expect(calls.content).toBe(0)
  await user.click(screen.getByRole('button', { name: 'Next' }))

  expect(await screen.findByText('41–45 of 45')).toBeInTheDocument()
  expect(location()).toBe(`/documents/${DOC.doc_id}?tab=chunks&cpage=3`)
  expect(calls.chunks.at(-1)?.get('offset')).toBe('40')
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
})

test('show vectors asks for them and shows a preview that copies in full', async () => {
  const calls = serve()
  const { user } = renderApp(`/documents/${DOC.doc_id}?tab=chunks`, { connected: true })
  await screen.findByRole('article', { name: 'Chunk 0' })

  await user.click(screen.getByRole('checkbox', { name: /Show vectors/ }))

  const first = await screen.findByRole('article', { name: 'Chunk 0' })
  expect(await within(first).findByText(/… 1024 values\]$/)).toHaveTextContent(
    '[0.0000, 0.1000, 0.2000',
  )
  expect(calls.chunks.at(-1)?.get('include_embedding')).toBe('true')
  expect(location()).toBe(`/documents/${DOC.doc_id}?tab=chunks`)
  await user.click(within(first).getByRole('button', { name: 'Copy vector' }))
  expect(JSON.parse(await navigator.clipboard.readText())).toHaveLength(1024)
})

test('a malformed id is not found without asking the API', async () => {
  // No handlers: a request would fail the test.
  renderApp('/documents/pro-014.md', { connected: true })

  expect(
    await screen.findByRole('heading', { name: 'This document no longer exists' }),
  ).toBeInTheDocument()
})

test.each(['detail', 'content', 'chunks'])(
  'a 404 from the %s shows the not-found page',
  async (part) => {
    serve()
    const url = { detail: BASE, content: `${BASE}/content`, chunks: `${BASE}/chunks` }[part]!
    server.use(http.get(url, notFound))
    renderApp(`/documents/${DOC.doc_id}${part === 'chunks' ? '?tab=chunks' : ''}`, {
      connected: true,
    })

    expect(
      await screen.findByRole('heading', { name: 'This document no longer exists' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to documents' })).toHaveAttribute(
      'href',
      '/documents',
    )
  },
)

test('an error in a tab stays in the tab, with retry', async () => {
  serve()
  let fail = true
  server.use(
    http.get(`${BASE}/content`, () =>
      fail
        ? HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
            { status: 500 },
          )
        : new HttpResponse('# Recuperado'),
    ),
  )
  const { user } = renderApp(`/documents/${DOC.doc_id}`, { connected: true })

  expect(await screen.findByRole('alert')).toHaveTextContent('internal server error')
  expect(screen.getByRole('heading', { name: 'PRO-014 Control de sellado' })).toBeInTheDocument()
  fail = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))

  expect(await screen.findByRole('heading', { name: 'Recuperado' })).toBeInTheDocument()
})

test('chunks show raw by default and can be rendered, kept in the URL', async () => {
  serve()
  const { user } = renderApp(`/documents/${DOC.doc_id}?tab=chunks`, { connected: true })
  const first = await screen.findByRole('article', { name: 'Chunk 0' })
  expect(
    within(screen.getByRole('group', { name: 'Chunk view' })).getByRole('button', { name: 'Raw' }),
  ).toHaveAttribute('aria-pressed', 'true')
  expect(first.querySelector('p.whitespace-pre-wrap')).toHaveTextContent('Paso 1: comprobar')

  await user.click(screen.getByRole('button', { name: 'Rendered' }))

  expect(location()).toBe(`/documents/${DOC.doc_id}?tab=chunks&cview=rendered`)
  const rendered = await screen.findByRole('article', { name: 'Chunk 0' })
  await waitFor(() => {
    expect(rendered.querySelector('.markdown')).not.toBeNull()
  })
})

describe('now differs', () => {
  test('a config that differs from the current settings says what changed', async () => {
    serve()
    const current = makeSettings()
    server.use(
      http.get(`${API}/admin/settings`, () =>
        HttpResponse.json({
          ...current,
          chunking: {
            ...current.chunking,
            chunk_size: 1000,
            chunker_config: current.chunking.chunker_config.replace('size=800', 'size=1000'),
          },
          embedding: {
            ...current.embedding,
            model: 'voyage-5',
            embedder_config: 'voyage-5/document/1024',
          },
        }),
      ),
    )
    renderApp(`/documents/${DOC.doc_id}`, { connected: true })

    const panel = await screen.findByRole('complementary', { name: 'Facts' })
    expect(await within(panel).findByText('Now differs: size 800 → 1000')).toBeInTheDocument()
    expect(within(panel).getByText('Now differs: model voyage-4 → voyage-5')).toBeInTheDocument()
  })

  test('nothing is noted when the configs match', async () => {
    serve()
    renderApp(`/documents/${DOC.doc_id}`, { connected: true })

    const panel = await screen.findByRole('complementary', { name: 'Facts' })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(within(panel).queryByText(/differs/i)).not.toBeInTheDocument()
  })
})

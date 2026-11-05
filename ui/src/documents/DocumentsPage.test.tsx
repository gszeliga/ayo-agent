import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { DOCUMENTS, makeDocument, TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

type Document = components['schemas']['Document']

/** Stands in for the API: filters by tenant and q, pages by limit/offset; records each query. */
function serve(documents: Document[] = DOCUMENTS, tenants = TENANTS) {
  const queries: URLSearchParams[] = []
  server.use(
    http.get(`${API}/admin/documents`, ({ request }) => {
      const query = new URL(request.url).searchParams
      queries.push(query)
      const tenant = query.get('tenant')
      const q = query.get('q')?.toLowerCase()
      const matching = documents.filter(
        (doc) =>
          (!tenant || doc.tenant === tenant) &&
          (!q || `${doc.title ?? ''} ${doc.source_key}`.toLowerCase().includes(q)),
      )
      const offset = Number(query.get('offset'))
      const limit = Number(query.get('limit'))
      return HttpResponse.json({
        items: matching.slice(offset, offset + limit),
        total: matching.length,
        limit,
        offset,
      })
    }),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(tenants)),
  )
  return queries
}

const location = () => screen.getByTestId('location').textContent
const rows = () =>
  within(screen.getByRole('table', { name: 'Documents' }))
    .getAllByRole('row')
    .slice(1)
const tenantsNav = () => screen.findByRole('navigation', { name: 'Tenants' })

function manyDocuments(count: number): Document[] {
  return Array.from({ length: count }, (_, i) =>
    makeDocument({
      title: `Procedimiento ${String(i + 1).padStart(3, '0')}`,
      source_key: `procedimiento-${String(i + 1)}.md`,
    }),
  )
}

test('rows show what the API returns', async () => {
  serve()
  renderApp('/documents', { connected: true })

  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })
  const [first, second, third] = rows()
  const link = within(first!).getByRole('link', { name: 'PRO-014 Control de sellado' })
  expect(link).toHaveAttribute('href', `/documents/${DOCUMENTS[0]!.doc_id}`)
  expect(first).toHaveTextContent('pro-014-control-sellado.md')
  expect(first).toHaveTextContent('planta-norte')
  expect(first).toHaveTextContent('Indexed')
  expect(first).toHaveTextContent('4.2 KB')
  expect(within(first!).getByText('3 h ago')).toHaveAttribute(
    'title',
    expect.stringMatching(/UTC$/),
  )
  expect(second).toHaveTextContent('Outdated: Chunking settings changed since it was indexed')
  expect(second).toHaveTextContent('1 d ago')
  expect(third).toHaveTextContent('6 min ago')
  expect(screen.getByText('3 documents')).toBeInTheDocument()
  expect(screen.getByText('1–3 of 3')).toBeInTheDocument()
})

test('a document without a recorded size shows a dash', async () => {
  serve([makeDocument({ size_bytes: null })])
  renderApp('/documents', { connected: true })

  await waitFor(() => {
    expect(rows()).toHaveLength(1)
  })
  expect(rows()[0]).toHaveTextContent('—')
})

test('clicking a row opens the document', async () => {
  serve()
  const { user } = renderApp('/documents', { connected: true })
  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })

  await user.click(within(rows()[2]!).getByText('arranque-linea-3.md'))

  expect(location()).toBe(`/documents/${DOCUMENTS[2]!.doc_id}`)
})

test('the request carries what the URL says', async () => {
  const queries = serve()
  renderApp('/documents?tenant=planta-sur&q=arranque&sort=title&page=1', { connected: true })

  await waitFor(() => {
    expect(rows()).toHaveLength(1)
  })
  expect(Object.fromEntries(queries.at(-1)!)).toEqual({
    tenant: 'planta-sur',
    q: 'arranque',
    sort: 'title',
    limit: '25',
    offset: '0',
  })
})

test('the sidebar lists tenants with counts and marks the selected one', async () => {
  serve()
  const { user } = renderApp('/documents?page=2&sort=title', { connected: true })

  const all = await within(await tenantsNav()).findByRole('link', { name: /All tenants/ })
  expect(all).toHaveTextContent('All tenants3')
  expect(all).toHaveAttribute('aria-current', 'page')

  await user.click(within(await tenantsNav()).getByRole('link', { name: /planta-sur/ }))

  // The sort is kept, the page goes back to 1.
  expect(location()).toBe('/documents?tenant=planta-sur&sort=title')
  expect(within(await tenantsNav()).getByRole('link', { name: /planta-sur/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await waitFor(() => {
    expect(rows()).toHaveLength(1)
  })
})

test('a selected tenant without documents is still listed, with 0', async () => {
  serve()
  renderApp('/documents?tenant=planta-este', { connected: true })

  const entry = await within(await tenantsNav()).findByRole('link', { name: /planta-este/ })
  expect(entry).toHaveTextContent('planta-este0')
  expect(entry).toHaveAttribute('aria-current', 'page')
})

test('the narrow-screen tenant select filters too', async () => {
  serve()
  const { user } = renderApp('/documents', { connected: true })

  await user.selectOptions(await screen.findByLabelText('Tenant'), 'planta-norte')

  expect(location()).toBe('/documents?tenant=planta-norte')
})

test('sorting updates the URL and goes back to page 1', async () => {
  const queries = serve(manyDocuments(30))
  const { user } = renderApp('/documents?page=2', { connected: true })
  await waitFor(() => {
    expect(rows()).toHaveLength(5)
  })

  await user.selectOptions(screen.getByLabelText('Sort'), 'Most chunks')

  expect(location()).toBe('/documents?sort=-chunk_count')
  await waitFor(() => {
    expect(queries.at(-1)?.get('sort')).toBe('-chunk_count')
  })
  expect(queries.at(-1)?.get('offset')).toBe('0')
})

test('typing a search sends one request once typing pauses', async () => {
  const queries = serve()
  const { user } = renderApp('/documents', { connected: true })
  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })

  await user.type(screen.getByLabelText('Search title or file name'), 'caldera')

  await waitFor(() => {
    expect(rows()).toHaveLength(1)
  })
  expect(location()).toBe('/documents?q=caldera')
  expect(queries.map((query) => query.get('q')).filter(Boolean)).toEqual(['caldera'])
})

test('next and previous move by a page', async () => {
  const queries = serve(manyDocuments(60))
  const { user } = renderApp('/documents', { connected: true })
  expect(await screen.findByText('1–25 of 60')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

  await user.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByText('26–50 of 60')).toBeInTheDocument()
  expect(location()).toBe('/documents?page=2')
  expect(queries.at(-1)?.get('offset')).toBe('25')

  await user.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByText('51–60 of 60')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()

  await user.click(screen.getByRole('button', { name: 'Previous' }))
  expect(await screen.findByText('26–50 of 60')).toBeInTheDocument()
})

test('a page past the end moves to the last page', async () => {
  serve(manyDocuments(30))
  renderApp('/documents?page=9', { connected: true })

  expect(await screen.findByText('26–30 of 30')).toBeInTheDocument()
  expect(location()).toBe('/documents?page=2')
})

test('an invalid URL is corrected in place', async () => {
  serve()
  renderApp('/documents?sort=size&page=0&tenant=Planta%20Norte', { connected: true })

  await waitFor(() => {
    expect(location()).toBe('/documents')
  })
})

test('back restores the previous view', async () => {
  serve()
  const { user } = renderApp('/documents', { connected: true })
  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })
  await user.click(within(await tenantsNav()).getByRole('link', { name: /planta-sur/ }))
  await waitFor(() => {
    expect(rows()).toHaveLength(1)
  })

  await user.click(screen.getByTestId('back'))

  expect(location()).toBe('/documents')
  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })
})

test('the search box follows the URL when it changes elsewhere', async () => {
  serve()
  const { user } = renderApp('/documents?q=sellado', { connected: true })
  const box = screen.getByLabelText('Search title or file name')
  expect(box).toHaveValue('sellado')

  await user.click(await screen.findByRole('button', { name: 'Clear filters' }))

  expect(box).toHaveValue('')
  expect(location()).toBe('/documents')
})

test('no documents at all', async () => {
  serve([], [])
  renderApp('/documents', { connected: true })

  expect(await screen.findByRole('heading', { name: 'No documents yet' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
})

test('filters that match nothing offer to clear them', async () => {
  serve()
  const { user } = renderApp('/documents?q=turbina&tenant=planta-sur', { connected: true })

  expect(await screen.findByRole('heading', { name: 'No documents match' })).toBeInTheDocument()
  const buttons = screen.getAllByRole('button', { name: 'Clear filters' })
  await user.click(buttons.at(-1)!)

  expect(location()).toBe('/documents')
  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })
})

test('the first load shows skeleton rows', () => {
  serve()
  renderApp('/documents', { connected: true })

  expect(screen.getByRole('table', { name: 'Loading documents' })).toHaveAttribute(
    'aria-busy',
    'true',
  )
})

test('an error shows its message and retry fetches again', async () => {
  let fail = true
  server.use(
    http.get(`${API}/admin/documents`, () =>
      fail
        ? HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
            { status: 500 },
          )
        : HttpResponse.json({ items: DOCUMENTS, total: 3, limit: 25, offset: 0 }),
    ),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
  )
  const { user } = renderApp('/documents', { connected: true })

  expect(await screen.findByRole('alert')).toHaveTextContent('internal server error')
  fail = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))

  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })
})

test('an unreachable API says so', async () => {
  server.use(
    http.get(`${API}/admin/documents`, () => HttpResponse.error()),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
  )
  renderApp('/documents', { connected: true })

  expect(await screen.findByRole('alert')).toHaveTextContent(`Can't reach the API at ${API}`)
})

test('reconnecting never shows rows cached before', async () => {
  serve()
  const { user } = renderApp('/documents', { connected: true })
  await waitFor(() => {
    expect(rows()).toHaveLength(3)
  })
  await user.click(screen.getByRole('button', { name: 'Disconnect' }))

  // The next connection's API answers slowly: the old rows must not show meanwhile.
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.json([])),
    http.get(`${API}/admin/documents`, async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
      return HttpResponse.json({ items: [], total: 0, limit: 25, offset: 0 })
    }),
  )
  await user.clear(screen.getByLabelText('API address'))
  await user.type(screen.getByLabelText('API address'), API)
  await user.type(screen.getByLabelText('Admin key'), 'another-key')
  await user.click(screen.getByRole('button', { name: 'Connect' }))

  expect(await screen.findByRole('table', { name: 'Loading documents' })).toBeInTheDocument()
  expect(screen.queryByText('PRO-014 Control de sellado')).not.toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'No documents yet' })).toBeInTheDocument()
})

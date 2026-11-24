import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { makeDocument, TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { BulkDeleteDialog } from './BulkDeleteDialog'

type Document = components['schemas']['Document']

function documents(count: number, tenant = 'planta-norte'): Document[] {
  return Array.from({ length: count }, (_, i) =>
    makeDocument({
      tenant,
      title: `Procedimiento ${String(i + 1).padStart(3, '0')}`,
      source_key: `procedimiento-${tenant}-${String(i + 1)}.md`,
      chunk_count: 2,
    }),
  )
}

/** A list that pages and filters, and a bulk delete that removes what it gets. */
function serve(
  initial: Document[],
  { bulk }: { bulk?: (ids: string[], call: number) => Response | undefined } = {},
) {
  let stored = [...initial]
  const requests: string[][] = []
  server.use(
    http.get(`${API}/admin/documents`, ({ request }) => {
      const query = new URL(request.url).searchParams
      const tenant = query.get('tenant')
      const q = query.get('q')?.toLowerCase()
      const matching = stored.filter(
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
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.post(`${API}/admin/documents/delete`, async ({ request }) => {
      const ids = ((await request.json()) as { doc_ids: string[] }).doc_ids
      requests.push(ids)
      const custom = bulk?.(ids, requests.length)
      if (custom) return custom
      const deleted = stored.filter((doc) => ids.includes(doc.doc_id))
      stored = stored.filter((doc) => !ids.includes(doc.doc_id))
      return HttpResponse.json({
        deleted: deleted.map((doc) => ({
          doc_id: doc.doc_id,
          tenant: doc.tenant,
          chunk_count: doc.chunk_count,
        })),
        not_found: ids.filter((id) => !deleted.some((doc) => doc.doc_id === id)),
      })
    }),
  )
  return {
    requests,
    remove: (ids: string[]) => {
      stored = stored.filter((doc) => !ids.includes(doc.doc_id))
    },
  }
}

const table = () => screen.getByRole('table', { name: 'Documents' })
const location = () => screen.getByTestId('location').textContent

async function openList(path = '/documents') {
  const rendered = renderApp(path, { connected: true })
  await screen.findByRole('table', { name: 'Documents' })
  return rendered
}

test('rows and select-all, with the indeterminate state', async () => {
  serve(documents(3))
  const { user } = await openList()
  const all = within(table()).getByRole('checkbox', { name: 'Select all on this page' })

  await user.click(within(table()).getByRole('checkbox', { name: 'Select Procedimiento 001' }))
  expect(all).toHaveAttribute('data-state', 'indeterminate')
  expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('1 selected')

  await user.click(all)
  expect(all).toHaveAttribute('data-state', 'checked')
  expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('3 selected')

  await user.click(all)
  expect(screen.queryByRole('region', { name: 'Selection' })).not.toBeInTheDocument()
})

test('a checkbox click does not open the document', async () => {
  serve(documents(2))
  const { user } = await openList()

  await user.click(within(table()).getByRole('checkbox', { name: 'Select Procedimiento 002' }))

  expect(location()).toBe('/documents')
})

test('the selection survives paging and counts what is on other pages', async () => {
  serve(documents(30))
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select Procedimiento 001' }))
  await user.click(within(table()).getByRole('checkbox', { name: 'Select Procedimiento 002' }))

  await user.click(screen.getByRole('button', { name: 'Next' }))
  await within(table()).findByRole('checkbox', { name: 'Select Procedimiento 026' })
  await user.click(within(table()).getByRole('checkbox', { name: 'Select Procedimiento 026' }))

  expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent(
    '3 selected (2 on other pages)',
  )
})

test('a new tenant or search clears the selection', async () => {
  serve([...documents(3), ...documents(2, 'planta-sur')])
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))

  await user.click(screen.getByRole('button', { name: 'Clear selection' }))
  expect(screen.queryByRole('region', { name: 'Selection' })).not.toBeInTheDocument()

  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  const nav = screen.getByRole('navigation', { name: 'Tenants' })
  await user.click(within(nav).getByRole('link', { name: /planta-sur/ }))

  await waitFor(() => {
    expect(screen.queryByRole('region', { name: 'Selection' })).not.toBeInTheDocument()
  })
})

test('the dialog lists five titles, counts chunks, and needs "delete N"', async () => {
  const { requests } = serve(documents(7))
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog', { name: 'Delete 7 documents?' })

  const listed = within(
    within(dialog).getByRole('list', { name: 'Documents to delete' }),
  ).getAllByRole('listitem')
  expect(listed.map((item) => item.textContent)).toEqual([
    'Procedimiento 001',
    'Procedimiento 002',
    'Procedimiento 003',
    'Procedimiento 004',
    'Procedimiento 005',
    'and 2 more',
  ])
  expect(dialog).toHaveTextContent('their 14 chunks are removed for good')
  const confirm = within(dialog).getByRole('button', { name: 'Delete' })
  await user.type(within(dialog).getByLabelText(/to confirm/), 'delete 6')
  expect(confirm).toBeDisabled()
  await user.clear(within(dialog).getByLabelText(/to confirm/))
  await user.type(within(dialog).getByLabelText(/to confirm/), 'delete 7')
  await user.click(confirm)

  expect(await screen.findByText('Deleted 7 documents')).toBeInTheDocument()
  expect(requests).toHaveLength(1)
  expect(requests[0]).toHaveLength(7)
  expect(screen.queryByRole('region', { name: 'Selection' })).not.toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'No documents yet' })).toBeInTheDocument()
})

test('ids already gone are reported, not errors', async () => {
  const { remove } = serve(documents(3))
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  const gone = within(table())
    .getAllByRole('link')
    .slice(0, 2)
    .map((link) => link.getAttribute('href')?.split('/').at(-1) ?? '')
  remove(gone) // deleted in another tab meanwhile

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog')
  await user.type(within(dialog).getByLabelText(/to confirm/), 'delete 3')
  await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

  expect(await screen.findByText('Deleted 1 document; 2 were already gone')).toBeInTheDocument()
})

test('more than 100 go in batches of 100', async () => {
  const { requests } = serve(documents(130))
  const { user } = await openList()
  for (let page = 1; page <= 6; page += 1) {
    await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
    if (page < 6) {
      await user.click(screen.getByRole('button', { name: 'Next' }))
      await within(table()).findByRole('checkbox', {
        name: `Select Procedimiento ${String(page * 25 + 1).padStart(3, '0')}`,
      })
    }
  }
  expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('130 selected')

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog')
  await user.type(within(dialog).getByLabelText(/to confirm/), 'delete 130')
  await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

  expect(await screen.findByText('Deleted 130 documents')).toBeInTheDocument()
  expect(requests.map((ids) => ids.length)).toEqual([100, 30])
  // Six pages selected one by one: about 1.6 s alone, near the default 5 s when every file
  // runs at once.
}, 15_000)

test('a failure keeps the selection and says why', async () => {
  serve(documents(3), {
    bulk: () =>
      HttpResponse.json(
        { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
        { status: 500 },
      ),
  })
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog')
  await user.type(within(dialog).getByLabelText(/to confirm/), 'delete 3')
  await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent('internal server error')
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('3 selected')
})

test('a batch failing after another succeeded says what was done, and keeps the rest', async () => {
  serve(documents(130), {
    bulk: (_ids, call) =>
      call === 2
        ? HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
            { status: 500 },
          )
        : undefined,
  })
  const { user } = await openList()
  for (let page = 1; page <= 6; page += 1) {
    await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
    if (page < 6) {
      await user.click(screen.getByRole('button', { name: 'Next' }))
      await within(table()).findByRole('checkbox', {
        name: `Select Procedimiento ${String(page * 25 + 1).padStart(3, '0')}`,
      })
    }
  }
  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog')
  await user.type(within(dialog).getByLabelText(/to confirm/), 'delete 130')
  await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent(
    'Deleted 100 documents, then it stopped: internal server error The rest are still selected.',
  )
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('30 selected')
  // 130 documents over six pages and two batches: about 1.8 s alone, 4.9 s when every file
  // runs at once (near the default 5 s).
}, 15_000)

describe('in Spanish', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function openListEs() {
    const rendered = renderApp('/documents', { connected: true, language: 'es' })
    await screen.findByRole('table', { name: 'Documentos' })
    return rendered
  }

  test('the dialog asks for "eliminar N", deletes, and says so', async () => {
    serve(documents(3))
    const { user } = await openListEs()
    await user.click(screen.getByRole('checkbox', { name: 'Seleccionar todos en esta página' }))
    await user.click(screen.getByRole('button', { name: 'Eliminar' }))

    const dialog = await screen.findByRole('alertdialog', { name: '¿Eliminar 3 documentos?' })
    expect(dialog).toHaveTextContent('junto con sus 6 chunks. No se puede deshacer.')
    expect(within(dialog).getByRole('list', { name: 'Documentos que se eliminan' })).toBeVisible()
    const input = within(dialog).getByLabelText('Escribe eliminar 3 para confirmar')
    expect(within(dialog).getByText('eliminar 3').tagName).toBe('STRONG')
    const confirm = within(dialog).getByRole('button', { name: 'Eliminar' })
    await user.type(input, 'delete 3')
    expect(confirm).toBeDisabled()
    await user.clear(input)
    await user.type(input, 'eliminar 3')
    await user.click(confirm)

    expect(await screen.findByText('Eliminados 3 documentos')).toBeInTheDocument()
  })

  test('documents already gone are counted apart', async () => {
    serve(documents(3))
    const { user } = await openListEs()
    await user.click(screen.getByRole('checkbox', { name: 'Seleccionar todos en esta página' }))
    await user.click(screen.getByRole('button', { name: 'Eliminar' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.type(within(dialog).getByLabelText(/para confirmar/), 'eliminar 3')
    server.use(
      http.post(`${API}/admin/documents/delete`, async ({ request }) => {
        const ids = ((await request.json()) as { doc_ids: string[] }).doc_ids
        return HttpResponse.json({
          deleted: [{ doc_id: ids[0], tenant: 'planta-norte', chunk_count: 2 }],
          not_found: ids.slice(1),
        })
      }),
    )
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))

    expect(await screen.findByText('Eliminado 1 documento; 2 ya no existían')).toBeInTheDocument()
  })

  test('a batch failing after another says what was done, and rewords on a switch', async () => {
    // The dialog alone: 101 selected without paging through the list.
    const selected = new Map(
      Array.from({ length: 101 }, (_, i) => [
        `upload-${String(i).padStart(12, '0')}`,
        { title: `Procedimiento ${String(i + 1)}`, chunks: 1 },
      ]),
    )
    let calls = 0
    server.use(
      http.post(`${API}/admin/documents/delete`, async ({ request }) => {
        calls += 1
        const ids = ((await request.json()) as { doc_ids: string[] }).doc_ids
        if (calls === 2) {
          return HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
            { status: 500 },
          )
        }
        return HttpResponse.json({
          deleted: ids.map((doc_id) => ({ doc_id, tenant: 'planta-norte', chunk_count: 1 })),
          not_found: [],
        })
      }),
    )
    // On System, the browser preferring Spanish.
    let browser = ['es-ES']
    vi.spyOn(navigator, 'languages', 'get').mockImplementation(() => browser)
    const routes = (
      <>
        <BulkDeleteDialog
          selected={selected}
          open
          onOpenChange={() => undefined}
          onDeleted={() => undefined}
        />
      </>
    )
    const { user } = renderApp('/', { connected: true, routes })
    const dialog = await screen.findByRole('alertdialog', { name: '¿Eliminar 101 documentos?' })
    expect(dialog).toHaveTextContent('y 96 más')
    await user.type(within(dialog).getByLabelText(/para confirmar/), 'eliminar 101')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Eliminados 100 documentos y después se ha detenido: internal server error El resto sigue' +
        ' seleccionado.',
    )

    // The failure is kept as is and worded when shown: the browser switches to English (the
    // header's menu is behind the modal dialog).
    browser = ['en-GB']
    act(() => {
      window.dispatchEvent(new Event('languagechange'))
    })
    expect(within(dialog).getByRole('alert')).toHaveTextContent(
      'Deleted 100 documents, then it stopped: internal server error The rest are still selected.',
    )
  })
})

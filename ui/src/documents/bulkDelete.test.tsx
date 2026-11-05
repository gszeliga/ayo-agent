import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { makeDocument, TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

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
})

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
})

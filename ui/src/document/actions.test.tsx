import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { makeDocument, TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { DOCUMENT_CHANGED, REPROCESS_PROVIDER_FAILED } from './ReprocessButton'

type Document = components['schemas']['Document']

const errorBody = (status: number, type: string, loc: (string | number)[], msg: string) => () =>
  HttpResponse.json({ detail: [{ type, loc, msg }] }, { status })

interface Calls {
  renames: unknown[]
  reprocesses: string[]
  deletes: number
}

/** One stored document behind every endpoint the detail page and the list use. */
function serve(
  initial: Partial<Document> = {},
  overrides: {
    rename?: () => Response
    reprocess?: () => Response | Promise<Response>
    remove?: () => Response
  } = {},
) {
  let doc = makeDocument({
    title: 'Manual de mantenimiento de la caldera B2',
    status: 'outdated',
    outdated_reason: 'chunker_changed',
    chunk_count: 48,
    ...initial,
  })
  const calls: Calls = { renames: [], reprocesses: [], deletes: 0 }
  const base = `${API}/admin/documents/${doc.doc_id}`
  server.use(
    http.get(base, () => HttpResponse.json(doc)),
    http.get(
      `${base}/content`,
      () => new HttpResponse('# Caldera B2\n\nPurgar antes de arrancar.'),
    ),
    http.patch(base, async ({ request }) => {
      const body = (await request.json()) as { title: string }
      calls.renames.push(body)
      if (overrides.rename) return overrides.rename()
      doc = { ...doc, title: body.title }
      return HttpResponse.json(doc)
    }),
    http.post(`${base}/reprocess`, ({ request }) => {
      calls.reprocesses.push(new URL(request.url).searchParams.get('force') ?? '')
      if (overrides.reprocess) return overrides.reprocess()
      doc = { ...doc, status: 'indexed', outdated_reason: null, chunk_count: 50 }
      return HttpResponse.json({
        doc_id: doc.doc_id,
        status: 'indexed',
        chunk_count: 50,
        embedding_model: 'voyage-4',
        embed_signature: 'f'.repeat(64),
      })
    }),
    http.delete(base, () => {
      calls.deletes += 1
      return overrides.remove ? overrides.remove() : new HttpResponse(null, { status: 204 })
    }),
    http.get(`${API}/admin/documents`, () =>
      HttpResponse.json({
        items: calls.deletes ? [] : [doc],
        total: calls.deletes ? 0 : 1,
        limit: 25,
        offset: 0,
      }),
    ),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
  )
  return { doc, calls }
}

const location = () => screen.getByTestId('location').textContent

async function openDetail(doc: Document, from = '') {
  const rendered = from
    ? renderApp(from, { connected: true })
    : renderApp(`/documents/${doc.doc_id}`, { connected: true })
  if (from) await rendered.user.click(await screen.findByRole('link', { name: doc.title ?? '' }))
  await screen.findByRole('heading', { name: doc.title ?? doc.source_key })
  return rendered
}

describe('rename', () => {
  test('Enter saves the trimmed title; header, list and tab title follow', async () => {
    const { doc, calls } = serve()
    const { user } = await openDetail(doc, '/documents')

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    const input = screen.getByLabelText('Title')
    expect(input).toHaveValue(doc.title)
    await user.clear(input)
    await user.type(input, '  Caldera B2: mantenimiento (rev. 4)  {Enter}')

    expect(
      await screen.findByRole('heading', { name: 'Caldera B2: mantenimiento (rev. 4)' }),
    ).toBeInTheDocument()
    expect(calls.renames).toEqual([{ title: 'Caldera B2: mantenimiento (rev. 4)' }])
    expect(await screen.findByText('Renamed')).toBeInTheDocument()
    expect(window.document.title).toBe('Caldera B2: mantenimiento (rev. 4) · AYO Admin')
    await user.click(within(screen.getByRole('main')).getByRole('link', { name: 'Documents' }))
    expect(
      await screen.findByRole('link', { name: 'Caldera B2: mantenimiento (rev. 4)' }),
    ).toBeInTheDocument()
  })

  test('Esc cancels without a request', async () => {
    const { doc, calls } = serve()
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.type(screen.getByLabelText('Title'), ' cambiado{Escape}')

    expect(screen.getByRole('heading', { name: doc.title ?? '' })).toBeInTheDocument()
    expect(calls.renames).toEqual([])
  })

  test.each([
    ['   ', 'Enter a title.'],
    ['x'.repeat(201), 'At most 200 characters.'],
  ])('%j is refused before sending', async (title, message) => {
    const { doc, calls } = serve()
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    const input = screen.getByLabelText('Title')
    await user.clear(input)
    await user.type(input, `${title}{Enter}`)

    expect(input).toHaveAccessibleDescription(message)
    expect(calls.renames).toEqual([])
  })

  test('an unchanged title just closes the editor', async () => {
    const { doc, calls } = serve()
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(calls.renames).toEqual([])
  })

  test('a 422 is shown under the input', async () => {
    const { doc } = serve(
      {},
      {
        rename: errorBody(
          422,
          'string_too_long',
          ['body', 'title'],
          'String should have at most 200 characters',
        ),
      },
    )
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.type(screen.getByLabelText('Title'), ' (rev. 4){Enter}')

    await waitFor(() => {
      expect(screen.getByLabelText('Title')).toHaveAccessibleDescription(
        'String should have at most 200 characters',
      )
    })
  })

  test('a 404 shows that the document is gone', async () => {
    const { doc } = serve(
      {},
      { rename: errorBody(404, 'document_not_found', ['path', 'doc_id'], 'document not found') },
    )
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.type(screen.getByLabelText('Title'), ' (rev. 4){Enter}')

    expect(
      await screen.findByRole('heading', { name: 'This document no longer exists' }),
    ).toBeInTheDocument()
  })
})

describe('reprocess', () => {
  test('a normal reprocess, then the badge turns indexed', async () => {
    const { doc, calls } = serve()
    const { user } = await openDetail(doc)
    expect(screen.getByText(/^Outdated/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Reprocess' }))

    expect(await screen.findByText('Reprocessed: 50 chunks')).toBeInTheDocument()
    expect(calls.reprocesses).toEqual(['false'])
    expect(await screen.findByText('Indexed')).toBeInTheDocument()
  })

  test('force is in the menu', async () => {
    const { doc, calls } = serve()
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'More reprocess options' }))
    await user.click(await screen.findByRole('menuitem', { name: /Force reprocess/ }))

    await waitFor(() => {
      expect(calls.reprocesses).toEqual(['true'])
    })
  })

  test('up to date says there was nothing to do', async () => {
    const { doc } = serve(
      {},
      { reprocess: () => HttpResponse.json({ doc_id: 'x', status: 'up_to_date' }) },
    )
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Reprocess' }))

    expect(await screen.findByText('Already up to date: nothing to do.')).toBeInTheDocument()
    expect(screen.getByText('Use Force reprocess to rebuild it anyway.')).toBeInTheDocument()
  })

  test('a 409 says a newer upload won, and Retry sends it again', async () => {
    const { doc, calls } = serve(
      {},
      { reprocess: errorBody(409, 'document_changed', [], 'document was replaced') },
    )
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Reprocess' }))
    expect(await screen.findByText(DOCUMENT_CHANGED)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(calls.reprocesses).toEqual(['false', 'false'])
    })
  })

  test('a 502 says nothing was written', async () => {
    const { doc } = serve(
      {},
      { reprocess: errorBody(502, 'embedding_failed', [], 'embedding provider failed') },
    )
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Reprocess' }))

    expect(await screen.findByText(REPROCESS_PROVIDER_FAILED)).toBeInTheDocument()
  })

  test('the buttons are disabled while it runs', async () => {
    const { doc } = serve(
      {},
      {
        reprocess: async () => {
          await delay('infinite')
          return HttpResponse.json({})
        },
      },
    )
    const { user } = await openDetail(doc)

    await user.click(screen.getByRole('button', { name: 'Reprocess' }))

    expect(await screen.findByRole('button', { name: 'Reprocessing…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'More reprocess options' })).toBeDisabled()
  })
})

describe('delete', () => {
  async function openDelete(doc: Document, from?: string) {
    const rendered = await openDetail(doc, from)
    await rendered.user.click(screen.getByRole('button', { name: 'Delete' }))
    return { ...rendered, dialog: await screen.findByRole('alertdialog') }
  }

  test('needs the exact title, then deletes and returns to the list as it was', async () => {
    const { doc, calls } = serve()
    const { user, dialog } = await openDelete(doc, '/documents?sort=title')
    expect(dialog).toHaveTextContent('The document and its 48 chunks are removed for good')
    const confirm = within(dialog).getByRole('button', { name: 'Delete' })
    const input = within(dialog).getByLabelText(/to confirm/)

    await user.type(input, 'manual de mantenimiento de la caldera b2')
    expect(confirm).toBeDisabled() // case matters
    await user.clear(input)
    await user.type(input, doc.title ?? '')
    await user.click(confirm)

    expect(await screen.findByText(`Deleted ${doc.title ?? ''}`)).toBeInTheDocument()
    expect(calls.deletes).toBe(1)
    await waitFor(() => {
      expect(location()).toBe('/documents?sort=title')
    })
  })

  test('without a title, the source key is typed', async () => {
    const { doc } = serve({ title: null, source_key: 'caldera-b2.md' })
    const { dialog } = await openDelete(doc)

    expect(within(dialog).getByLabelText(/to confirm/)).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Type caldera-b2.md to confirm')
  })

  test('a 404 means it was already gone', async () => {
    const { doc } = serve(
      {},
      { remove: errorBody(404, 'document_not_found', ['path', 'doc_id'], 'document not found') },
    )
    const { user, dialog } = await openDelete(doc)

    await user.type(within(dialog).getByLabelText(/to confirm/), doc.title ?? '')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText(`${doc.title ?? ''} was already deleted`)).toBeInTheDocument()
    await waitFor(() => {
      expect(location()).toBe('/documents')
    })
  })

  test('another error stays in the dialog', async () => {
    const { doc } = serve(
      {},
      { remove: errorBody(500, 'internal_error', [], 'internal server error') },
    )
    const { user, dialog } = await openDelete(doc)

    await user.type(within(dialog).getByLabelText(/to confirm/), doc.title ?? '')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('internal server error')
  })
})

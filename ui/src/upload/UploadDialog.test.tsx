// @vitest-environment happy-dom
// @vitest-environment-options {"url": "http://api.test/"}
// jsdom cannot send a file through fetch here: its typed arrays come from another realm,
// so the multipart body is miscounted (RequestContentLengthMismatchError). happy-dom runs
// in Node's own realm. Browsers are not affected. The page shares the mocked API's origin, as
// behind the production proxy, so happy-dom sends no CORS preflights.

import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { DOCUMENTS, makeDocument, TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { CANCELLED_NOTE } from './UploadDialog'
import { EXISTING_CHECK_DELAY_MS } from './useExistingDocument'
import { PROVIDER_FAILED } from './useUpload'

type Document = components['schemas']['Document']

const MAX_BYTES = 1000
const PROCEDURE = '# PRO-021 Cambio de cuchillas\n\nDetener la línea y bloquear la energía.\n'

function markdownFile(name = 'pro-021-cambio-cuchillas.md', content = PROCEDURE) {
  return new File([content], name, { type: 'text/markdown' })
}

const errorBody = (status: number, type: string, loc: (string | number)[], msg: string) => () =>
  HttpResponse.json({ detail: [{ type, loc, msg }] }, { status })

interface Calls {
  uploads: Record<string, string>[]
  listQueries: URLSearchParams[]
}

/** The API around the dialog; records uploads (as their form fields) and list queries. */
function serve({
  documents = DOCUMENTS,
  upload = () =>
    HttpResponse.json(
      {
        doc_id: 'upload-0000000000aa',
        status: 'indexed',
        chunk_count: 3,
        embedding_model: 'voyage-4',
        embed_signature: 'e'.repeat(64),
      },
      { status: 201 },
    ),
  settings = true,
}: {
  documents?: Document[]
  upload?: () => Response | Promise<Response>
  settings?: boolean
} = {}): Calls {
  const calls: Calls = { uploads: [], listQueries: [] }
  server.use(
    http.get(`${API}/admin/documents`, ({ request }) => {
      const query = new URL(request.url).searchParams
      calls.listQueries.push(query)
      const tenant = query.get('tenant')
      const q = query.get('q')?.toLowerCase()
      const items = documents.filter(
        (doc) =>
          (!tenant || doc.tenant === tenant) &&
          (!q || `${doc.title ?? ''} ${doc.source_key}`.toLowerCase().includes(q)),
      )
      return HttpResponse.json({ items, total: items.length, limit: 25, offset: 0 })
    }),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/settings`, () =>
      settings
        ? HttpResponse.json({
            chunking: {
              chunker_version: 'v3',
              chunk_size: 800,
              chunk_overlap: 80,
              min_chunk_size: 100,
              chunker_config: 'c',
            },
            embedding: {
              provider: 'fake',
              model: 'voyage-4',
              dimensions: 1024,
              batch_size: 128,
              embedder_config: 'e',
            },
            uploads: { max_upload_bytes: MAX_BYTES },
            documents: {
              total: 3,
              indexed: 2,
              outdated: { unknown: 0, chunker_changed: 1, embedder_changed: 0 },
            },
          })
        : HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'x' }] },
            { status: 500 },
          ),
    ),
    http.post(`${API}/admin/documents`, async ({ request }) => {
      const form = await request.formData()
      const fields: Record<string, string> = {}
      form.forEach((value, key) => {
        fields[key] = typeof value === 'string' ? value : `file:${value.name}:${String(value.size)}`
      })
      calls.uploads.push(fields)
      return upload()
    }),
    http.get(`${API}/admin/documents/:docId`, ({ params }) =>
      HttpResponse.json(
        DOCUMENTS.find((doc) => doc.doc_id === params.docId) ??
          makeDocument({ doc_id: params.docId as string, title: 'PRO-021 Cambio de cuchillas' }),
      ),
    ),
    http.get(`${API}/admin/documents/:docId/content`, () => new HttpResponse(PROCEDURE)),
  )
  return calls
}

async function openUpload(path = '/documents') {
  const rendered = renderApp(path, { connected: true })
  await screen.findByRole('table', { name: 'Documents' })
  await rendered.user.click(screen.getByRole('button', { name: 'Upload' }))
  return { ...rendered, dialog: await screen.findByRole('dialog', { name: 'Upload a document' }) }
}

const location = () => screen.getByTestId('location').textContent

test('an upload sends the fields as entered, then opens the new document', async () => {
  const calls = serve()
  const { user, dialog } = await openUpload()
  const listCallsBefore = calls.listQueries.length

  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-este')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  expect(
    await screen.findByText('Indexed pro-021-cambio-cuchillas.md: 3 chunks'),
  ).toBeInTheDocument()
  expect(calls.uploads).toEqual([
    {
      file: `file:pro-021-cambio-cuchillas.md:${String(new Blob([PROCEDURE]).size)}`,
      tenant: 'planta-este',
    },
  ])
  await waitFor(() => {
    expect(location()).toBe('/documents/upload-0000000000aa')
  })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(calls.listQueries.length).toBeGreaterThan(listCallsBefore) // the list was refreshed
})

test('title, source key and force are sent when given', async () => {
  const calls = serve()
  const { user, dialog } = await openUpload('/documents?tenant=planta-sur')

  expect(within(dialog).getByLabelText('Tenant')).toHaveValue('planta-sur') // the list's filter
  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.type(within(dialog).getByLabelText('Title (optional)'), '  PRO-021 Cuchillas  ')
  await user.click(within(dialog).getByRole('button', { name: 'Advanced' }))
  await user.type(within(dialog).getByLabelText('Source key'), 'pro-021.md')
  await user.click(within(dialog).getByRole('checkbox', { name: /Force reindex/ }))
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  await waitFor(() => {
    expect(calls.uploads).toHaveLength(1)
  })
  expect(calls.uploads[0]).toMatchObject({
    tenant: 'planta-sur',
    title: 'PRO-021 Cuchillas',
    source_key: 'pro-021.md',
    force: 'true',
  })
})

test.each([
  ['notas.txt', PROCEDURE, 'Choose a Markdown file (.md).'],
  ['vacio.md', '', 'The file is empty.'],
  ['grande.md', 'x'.repeat(MAX_BYTES + 1), 'Larger than the 1000 B limit.'],
])('%s is refused before sending', async (name, content, message) => {
  const calls = serve()
  const { user, dialog } = await openUpload()

  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile(name, content))
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  expect(within(dialog).getByLabelText('Markdown file')).toHaveAccessibleDescription(message)
  expect(calls.uploads).toHaveLength(0)
})

test('the tenant is checked as typed, and required', async () => {
  const calls = serve()
  const { user, dialog } = await openUpload()
  const tenant = within(dialog).getByLabelText('Tenant')
  expect(tenant).toHaveAccessibleDescription(
    'Lowercase letters, digits and hyphens, 2–63 characters.',
  )

  await user.type(tenant, 'Planta Norte')
  expect(tenant).toHaveAttribute('aria-invalid', 'true')

  await user.clear(tenant)
  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))
  expect(tenant).toHaveAccessibleDescription('Enter a tenant.')
  expect(calls.uploads).toHaveLength(0)
})

test('the existing tenants are suggested', async () => {
  serve()
  const { dialog } = await openUpload()

  const list = within(dialog).getByLabelText('Tenant').getAttribute('list') ?? ''
  await waitFor(() => {
    expect(
      Array.from(document.querySelectorAll(`datalist[id="${list}"] option`), (o) =>
        o.getAttribute('value'),
      ),
    ).toEqual(['planta-norte', 'planta-sur'])
  })
})

test('without the settings, the size is left to the API (413)', async () => {
  serve({
    settings: false,
    upload: errorBody(413, 'file_too_large', ['body', 'file'], 'too large'),
  })
  const { user, dialog } = await openUpload()

  await user.upload(
    within(dialog).getByLabelText('Markdown file'),
    markdownFile('grande.md', 'x'.repeat(MAX_BYTES + 1)),
  )
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  await waitFor(() => {
    expect(within(dialog).getByLabelText('Markdown file')).toHaveAccessibleDescription(
      'The file is larger than the upload limit.',
    )
  })
})

test.each([
  ['file_encoding', ['body', 'file'], 'file must be UTF-8 text', 'Markdown file'],
  ['file_no_content', ['body', 'file'], 'file has no indexable content', 'Markdown file'],
  [
    'string_pattern_mismatch',
    ['body', 'tenant'],
    "String should match pattern '^[a-z0-9]'",
    'Tenant',
  ],
  [
    'source_key_invalid',
    ['body', 'source_key'],
    'source_key must contain a file name',
    'Source key',
  ],
])('a 422 %s is shown next to its field', async (type, loc, msg, label) => {
  serve({ upload: errorBody(422, type, loc, msg) })
  const { user, dialog } = await openUpload()

  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  // The Advanced section opens by itself for a source key error.
  expect(await within(dialog).findByLabelText(label)).toHaveAccessibleDescription(msg)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

test('a provider failure keeps the dialog and its input', async () => {
  serve({ upload: errorBody(502, 'embedding_failed', [], 'embedding provider failed') })
  const { user, dialog } = await openUpload()

  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent(PROVIDER_FAILED)
  expect(within(dialog).getByText('pro-021-cambio-cuchillas.md')).toBeInTheDocument()
  expect(within(dialog).getByLabelText('Tenant')).toHaveValue('planta-norte')
})

test('an up-to-date upload says nothing changed', async () => {
  serve({ upload: () => HttpResponse.json({ doc_id: DOCUMENTS[0]!.doc_id, status: 'up_to_date' }) })
  const { user, dialog } = await openUpload()

  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

  expect(await screen.findByText('Already up to date: nothing changed.')).toBeInTheDocument()
  expect(screen.getByText('Use Force reindex to rebuild it anyway.')).toBeInTheDocument()
})

test('uploading over an existing document warns first', async () => {
  const calls = serve()
  const { user, dialog } = await openUpload()

  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.upload(
    within(dialog).getByLabelText('Markdown file'),
    markdownFile('pro-014-control-sellado.md'),
  )

  const warning = await within(dialog).findByRole(
    'status',
    {},
    { timeout: EXISTING_CHECK_DELAY_MS + 1000 },
  )
  expect(warning).toHaveTextContent(
    'A document with this name already exists in planta-norte: uploading replaces it (PRO-014 Control de sellado, updated 3 h ago).',
  )
  // One check, after typing paused, for the exact tenant and source key.
  const checks = calls.listQueries.filter((query) => query.get('q') !== null)
  expect(checks.map((query) => [query.get('tenant'), query.get('q')])).toEqual([
    ['planta-norte', 'pro-014-control-sellado.md'],
  ])
})

test('a partial name match is not a warning', async () => {
  serve()
  const { user, dialog } = await openUpload()

  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.upload(
    within(dialog).getByLabelText('Markdown file'),
    markdownFile('control-sellado.md'),
  )
  await new Promise((resolve) => setTimeout(resolve, EXISTING_CHECK_DELAY_MS + 200))

  expect(within(dialog).queryByText(/already exists/)).not.toBeInTheDocument()
})

test('while sending, Esc does not close; Cancel aborts and says what that means', async () => {
  serve({
    upload: async () => {
      await delay('infinite')
      return HttpResponse.json({})
    },
  })
  const { user, dialog } = await openUpload()
  await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
  await user.type(within(dialog).getByLabelText('Tenant'), 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))
  expect(
    await within(dialog).findByRole('button', { name: 'Uploading and indexing…' }),
  ).toBeDisabled()

  await user.keyboard('{Escape}')
  expect(screen.getByRole('dialog')).toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(CANCELLED_NOTE)
})

describe('replace', () => {
  const doc = DOCUMENTS[1]! // renamed: its title is not its first heading

  async function openReplace() {
    const rendered = renderApp(`/documents/${doc.doc_id}`, { connected: true })
    await rendered.user.click(await screen.findByRole('button', { name: 'Replace' }))
    return { ...rendered, dialog: await screen.findByRole('dialog', { name: 'Replace document' }) }
  }

  test('keeps the tenant and source key, prefills the title, and stays on the page', async () => {
    const calls = serve({
      upload: () =>
        HttpResponse.json(
          {
            doc_id: doc.doc_id,
            status: 'indexed',
            chunk_count: 50,
            embedding_model: 'voyage-4',
            embed_signature: 'f'.repeat(64),
          },
          { status: 201 },
        ),
    })
    const { user, dialog } = await openReplace()

    expect(within(dialog).queryByLabelText('Tenant')).not.toBeInTheDocument()
    expect(dialog).toHaveTextContent(`Tenant${doc.tenant}`)
    expect(dialog).toHaveTextContent(`Source key${doc.source_key}`)
    expect(within(dialog).getByLabelText('Title (optional)')).toHaveValue(doc.title)
    await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile('caldera-v2.md'))
    await user.click(within(dialog).getByRole('button', { name: 'Replace' }))

    expect(await screen.findByText(`Replaced ${doc.title ?? ''}: 50 chunks`)).toBeInTheDocument()
    expect(calls.uploads[0]).toMatchObject({
      tenant: doc.tenant,
      source_key: doc.source_key,
      title: doc.title,
    })
    expect(location()).toBe(`/documents/${doc.doc_id}`)
  })

  test('does not warn about replacing: that is the point', async () => {
    const calls = serve()
    const { user, dialog } = await openReplace()

    await user.upload(within(dialog).getByLabelText('Markdown file'), markdownFile())
    await new Promise((resolve) => setTimeout(resolve, EXISTING_CHECK_DELAY_MS + 200))

    expect(within(dialog).queryByText(/already exists/)).not.toBeInTheDocument()
    expect(calls.listQueries.filter((query) => query.get('q') !== null)).toHaveLength(0)
  })
})

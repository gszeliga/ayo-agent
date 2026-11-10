import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { a11yViolations } from '@/test/axe'
import { makeDocument, TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

type Document = components['schemas']['Document']

function outdated(count: number): Document[] {
  return Array.from({ length: count }, (_, i) =>
    makeDocument({
      title: `Procedimiento ${String(i + 1).padStart(3, '0')}`,
      source_key: `procedimiento-${String(i + 1)}.md`,
      status: 'outdated',
      outdated_reason: 'chunker_changed',
      hoursAgo: i,
    }),
  )
}

/** A promise a handler waits on until the test calls `release`. */
function makeGate() {
  let release: () => void = () => {
    throw new Error('gate not ready')
  }
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  return { gate, release }
}

const error = (status: number, type: string, msg: string) =>
  HttpResponse.json({ detail: [{ type, loc: [], msg }] }, { status })

/**
 * A list that filters by status and pages, and a reprocess that marks the document indexed.
 * `answer` overrides the reprocess for a document (by its position in `initial`, 0-based).
 */
function serve(
  initial: Document[],
  {
    answer,
  }: { answer?: (index: number) => Promise<Response | undefined> | Response | undefined } = {},
) {
  const stored = initial.map((doc) => ({ ...doc }))
  const lists: URLSearchParams[] = []
  const reprocessed: string[] = []
  server.use(
    http.get(`${API}/admin/documents`, ({ request }) => {
      const query = new URL(request.url).searchParams
      lists.push(query)
      const status = query.get('status')
      const matching = stored.filter((doc) => !status || doc.status === status)
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
    http.post(`${API}/admin/documents/:docId/reprocess`, async ({ params, request }) => {
      const docId = params.docId as string
      expect(new URL(request.url).searchParams.get('force')).toBe('false')
      reprocessed.push(docId)
      const index = stored.findIndex((doc) => doc.doc_id === docId)
      const custom = await answer?.(index)
      if (custom) return custom
      const doc = stored[index]!
      const wasIndexed = doc.status === 'indexed'
      doc.status = 'indexed'
      doc.outdated_reason = null
      return HttpResponse.json(
        wasIndexed
          ? { doc_id: docId, status: 'up_to_date' }
          : {
              doc_id: docId,
              status: 'indexed',
              chunk_count: doc.chunk_count,
              embedding_model: 'voyage-4',
              embed_signature: doc.embed_signature,
            },
      )
    }),
  )
  return { lists, reprocessed }
}

const table = () => screen.getByRole('table', { name: 'Documents' })
const dialog = () => screen.getByRole('alertdialog')
const selectionBar = () => screen.queryByRole('region', { name: 'Selection' })

async function openList(path = '/documents') {
  const rendered = renderApp(path, { connected: true })
  await screen.findByRole('table', { name: 'Documents' })
  return rendered
}

test('the selection is reprocessed, summarised, and the settled ones leave it', async () => {
  const docs = [
    ...outdated(2),
    makeDocument({ title: 'Ya indexado', source_key: 'ya.md', hoursAgo: 9 }),
  ]
  const api = serve(docs, {
    answer: (index) =>
      index === 1 ? error(409, 'document_changed', 'replaced meanwhile') : undefined,
  })
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))

  await user.click(within(selectionBar()!).getByRole('button', { name: 'Reprocess' }))
  expect(dialog()).toHaveAccessibleName('Reprocess 3 documents?')
  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))

  const summary = await screen.findByRole('alertdialog', { name: 'Reprocess finished' })
  expect(api.reprocessed).toEqual(docs.map((doc) => doc.doc_id))
  const outcome = within(summary).getByRole('group', { name: 'Outcome' })
  expect(outcome).toHaveTextContent('Reprocessed1')
  expect(outcome).toHaveTextContent('Already up to date1')
  expect(outcome).toHaveTextContent('Replaced by a newer upload meanwhile1')
  expect(summary).toHaveTextContent('The ones not settled are still selected.')

  await user.click(within(summary).getByRole('button', { name: 'Close' }))
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  expect(selectionBar()).toHaveTextContent('1 selected')
})

test('"Reprocess all outdated" runs every match, pages included, then refreshes', async () => {
  const api = serve(outdated(101))
  const { user } = await openList('/documents?status=outdated')

  await user.click(screen.getByRole('button', { name: 'Reprocess all 101 outdated' }))
  expect(dialog()).toHaveAccessibleName('Reprocess 101 documents?')
  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))

  const summary = await screen.findByRole(
    'alertdialog',
    { name: 'Reprocess finished' },
    { timeout: 15_000 },
  )
  expect(within(summary).getByRole('group', { name: 'Outcome' })).toHaveTextContent(
    'Reprocessed101',
  )
  expect(new Set(api.reprocessed).size).toBe(101)
  const collected = api.lists.filter((query) => query.get('limit') === '100')
  expect(collected.map((query) => [query.get('status'), query.get('offset')])).toEqual([
    ['outdated', '0'],
    ['outdated', '100'],
  ])

  await user.click(within(summary).getByRole('button', { name: 'Close' }))
  // The list was refetched: nothing is outdated any more.
  expect(await screen.findByRole('heading', { name: 'No documents match' })).toBeInTheDocument()
}, 20_000)

test('the button shows only on the outdated filter with matches', async () => {
  serve(outdated(2))
  await openList()

  expect(screen.queryByRole('button', { name: /Reprocess all/ })).not.toBeInTheDocument()
})

test('stop finishes the current document and starts no other', async () => {
  const { gate, release } = makeGate()
  const api = serve(outdated(3), {
    answer: async (index) => {
      if (index === 0) await gate
      return undefined
    },
  })
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  await user.click(within(selectionBar()!).getByRole('button', { name: 'Reprocess' }))
  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))

  const running = await screen.findByRole('alertdialog', { name: 'Reprocessing documents' })
  expect(running).toHaveTextContent('0 of 3 done')
  expect(running).toHaveTextContent('Now: Procedimiento 001')
  await user.click(within(running).getByRole('button', { name: 'Stop' }))
  expect(running).toHaveTextContent('Stopping after this document…')
  release()

  const summary = await screen.findByRole('alertdialog', { name: 'Reprocess stopped' })
  expect(api.reprocessed).toHaveLength(1)
  expect(summary).toHaveTextContent('Stopped at your request.')
  expect(within(summary).getByRole('group', { name: 'Outcome' })).toHaveTextContent('Not started2')
})

test('the dialog cannot be closed while running', async () => {
  const { gate, release } = makeGate()
  serve(outdated(1), {
    answer: async () => {
      await gate
      return undefined
    },
  })
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  await user.click(within(selectionBar()!).getByRole('button', { name: 'Reprocess' }))
  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))
  await screen.findByRole('alertdialog', { name: 'Reprocessing documents' })

  await user.keyboard('{Escape}')

  expect(screen.getByRole('alertdialog', { name: 'Reprocessing documents' })).toBeInTheDocument()
  release()
  expect(await screen.findByRole('alertdialog', { name: 'Reprocess finished' })).toBeInTheDocument()
})

test('a provider failure stops the run and says where and why', async () => {
  const api = serve(outdated(4), {
    answer: (index) =>
      index === 1 ? error(502, 'embedding_failed', 'embedding provider failed') : undefined,
  })
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  await user.click(within(selectionBar()!).getByRole('button', { name: 'Reprocess' }))
  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))

  const summary = await screen.findByRole('alertdialog', { name: 'Reprocess stopped' })
  expect(api.reprocessed).toHaveLength(2)
  expect(within(summary).getByRole('alert')).toHaveTextContent(
    'Stopped at “Procedimiento 002”: The embedding provider failed; nothing was written.',
  )
  const outcome = within(summary).getByRole('group', { name: 'Outcome' })
  expect(outcome).toHaveTextContent('Reprocessed1')
  expect(outcome).toHaveTextContent('Failed1')
  expect(outcome).toHaveTextContent('Not started2')

  await user.click(within(summary).getByRole('button', { name: 'Close' }))
  expect(selectionBar()).toHaveTextContent('3 selected')
})

test('a failure while collecting the documents stays on the confirmation', async () => {
  serve(outdated(2))
  const { user } = await openList('/documents?status=outdated')
  server.use(
    http.get(`${API}/admin/documents`, ({ request }) =>
      new URL(request.url).searchParams.get('limit') === '100'
        ? error(500, 'internal', 'The API answered HTTP 500')
        : undefined,
    ),
  )

  await user.click(screen.getByRole('button', { name: 'Reprocess all 2 outdated' }))
  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))

  expect(await within(dialog()).findByRole('alert')).toHaveTextContent('The API answered HTTP 500')
  expect(dialog()).toHaveAccessibleName('Reprocess 2 documents?')
  expect(within(dialog()).getByRole('button', { name: 'Start' })).toBeEnabled()
})

test('each stage passes the accessibility baseline', async () => {
  const { gate, release } = makeGate()
  serve(outdated(2), {
    answer: async (index) => {
      if (index === 0) await gate
      return undefined
    },
  })
  const { user } = await openList()
  await user.click(within(table()).getByRole('checkbox', { name: 'Select all on this page' }))
  await user.click(within(selectionBar()!).getByRole('button', { name: 'Reprocess' }))
  expect(await a11yViolations()).toEqual([])

  await user.click(within(dialog()).getByRole('button', { name: 'Start' }))
  await screen.findByRole('alertdialog', { name: 'Reprocessing documents' })
  expect(await a11yViolations()).toEqual([])

  release()
  await screen.findByRole('alertdialog', { name: 'Reprocess finished' })
  expect(await a11yViolations()).toEqual([])
})

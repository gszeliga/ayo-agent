import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { CHUNKER_CONFIG, makeHealth, makeSettings } from '@/test/fixtures/services'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

const card = (name: string) => screen.getByRole('region', { name })

async function openSettings() {
  const rendered = renderApp('/settings', { connected: true })
  await screen.findByRole('region', { name: 'Chunking' })
  return rendered
}

test('each card shows its values and the variables that set them', async () => {
  await openSettings()

  const chunking = card('Chunking')
  expect(chunking).toHaveTextContent('Chunk sizeCHUNK_SIZE800 characters')
  expect(chunking).toHaveTextContent('OverlapCHUNK_OVERLAP80 characters')
  expect(chunking).toHaveTextContent('Minimum chunk sizeMIN_CHUNK_SIZE100 characters')
  expect(chunking).toHaveTextContent(CHUNKER_CONFIG)
  const embeddings = card('Embeddings')
  expect(embeddings).toHaveTextContent('ProviderEMBEDDING_PROVIDERvoyage')
  expect(embeddings).toHaveTextContent('DimensionsEMBEDDING_DIMENSIONS1024')
  expect(embeddings).toHaveTextContent('Batch sizeEMBEDDING_BATCH_SIZE128 texts per request')
  expect(within(embeddings).queryByRole('note')).not.toBeInTheDocument()
  expect(card('Uploads')).toHaveTextContent('Largest fileMAX_UPLOAD_BYTES5.0 MB')
})

test('documents: indexed, and outdated by reason', async () => {
  await openSettings()

  const documents = card('Documents')
  expect(documents).toHaveTextContent('12 stored')
  expect(documents).toHaveTextContent('Indexed with the current settings9')
  expect(documents).toHaveTextContent('Outdated3')
  expect(documents).toHaveTextContent('Chunking settings changed since it was indexed2')
  expect(documents).toHaveTextContent('Embedding model or size changed since it was indexed1')
  expect(documents).toHaveTextContent('3 documents are outdated: reprocess a document')
})

test('the fake provider is flagged', async () => {
  server.use(
    http.get(`${API}/admin/settings`, () =>
      HttpResponse.json(
        makeSettings({
          embedding: {
            provider: 'fake',
            model: 'voyage-4',
            dimensions: 1024,
            batch_size: 128,
            embedder_config: 'voyage-4/document/1024',
          },
        }),
      ),
    ),
  )
  await openSettings()

  expect(within(card('Embeddings')).getByRole('note')).toHaveTextContent('carry no meaning')
})

test('configs copy in full', async () => {
  const { user } = await openSettings()

  await user.click(within(card('Chunking')).getByRole('button', { name: 'Copy chunker config' }))

  expect(await navigator.clipboard.readText()).toBe(CHUNKER_CONFIG)
})

test('an error offers retry', async () => {
  let fail = true
  server.use(
    http.get(`${API}/admin/settings`, () =>
      fail
        ? HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'internal server error' }] },
            { status: 500 },
          )
        : HttpResponse.json(makeSettings()),
    ),
  )
  const { user } = renderApp('/settings', { connected: true })

  expect(await screen.findByRole('alert')).toHaveTextContent('internal server error')
  fail = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))

  expect(await screen.findByRole('region', { name: 'Chunking' })).toBeInTheDocument()
})

describe('service status', () => {
  function serveHealth(answers: ((refresh: string | null) => Response)[]) {
    const queries: (string | null)[] = []
    server.use(
      http.get(`${API}/admin/health`, ({ request }) => {
        const refresh = new URL(request.url).searchParams.get('refresh')
        queries.push(refresh)
        const answer = answers[Math.min(queries.length, answers.length) - 1]
        return answer ? answer(refresh) : HttpResponse.json(makeHealth())
      }),
    )
    return queries
  }

  const indicator = () => screen.getByRole('button', { name: /^Service status/ })

  test('green dots, and the details in a popover', async () => {
    serveHealth([() => HttpResponse.json(makeHealth())])
    const { user } = renderApp('/settings', { connected: true })

    await waitFor(() => {
      expect(indicator()).toHaveAccessibleName('Service status: database up, embeddings up')
    })
    await user.click(indicator())

    const popover = await screen.findByRole('dialog')
    expect(within(popover).getByRole('region', { name: 'Database service' })).toHaveTextContent(
      'Database: UpRuns onLocalVersionPostgreSQL 18.1 · pgvector 0.8.1Latency3 ms',
    )
    const embeddings = within(popover).getByRole('region', { name: 'Embeddings service' })
    expect(embeddings).toHaveTextContent('Providervoyage')
    expect(embeddings).toHaveTextContent('Last success1 h ago')
    expect(embeddings).toHaveTextContent('Last errornone since the API started')
  })

  test('a provider that is down shows red with its error', async () => {
    serveHealth([
      () =>
        HttpResponse.json(
          makeHealth({
            embeddings: {
              status: 'down',
              error: 'Embedding provider returned HTTP 503',
              cached: true,
              last_error: 'Embedding provider returned HTTP 503',
              last_error_at: new Date().toISOString(),
            },
          }),
        ),
    ])
    const { user } = renderApp('/settings', { connected: true })

    await waitFor(() => {
      expect(indicator()).toHaveAccessibleName('Service status: database up, embeddings down')
    })
    await user.click(indicator())
    const embeddings = within(await screen.findByRole('dialog')).getByRole('region', {
      name: 'Embeddings service',
    })
    expect(embeddings).toHaveTextContent('Embeddings: Down')
    expect(embeddings).toHaveTextContent('ErrorEmbedding provider returned HTTP 503')
    expect(embeddings).toHaveTextContent('(cached)')
  })

  test('check now asks with refresh=true and updates header and card alike', async () => {
    const queries = serveHealth([
      () => HttpResponse.json(makeHealth({ embeddings: { status: 'down', error: 'unreachable' } })),
      () => HttpResponse.json(makeHealth()),
    ])
    const { user } = await openSettings()
    await waitFor(() => {
      expect(indicator()).toHaveAccessibleName(/embeddings down/)
    })
    expect(queries).toEqual(['false']) // one request for the header and the card

    await user.click(within(card('Services')).getByRole('button', { name: 'Check now' }))

    await waitFor(() => {
      expect(indicator()).toHaveAccessibleName('Service status: database up, embeddings up')
    })
    expect(card('Services')).toHaveTextContent('Embeddings: Up')
    expect(queries).toEqual(['false', 'true'])
  })

  test('an unreachable status endpoint shows status unknown', async () => {
    serveHealth([() => HttpResponse.error()])
    renderApp('/settings', { connected: true })

    await waitFor(() => {
      expect(indicator()).toHaveAccessibleName(
        'Service status: database status unknown, embeddings status unknown',
      )
    })
  })

  test.each([
    ['neon', '18.1', null, 'Runs onNeonVersionPostgreSQL 18.1Latency'],
    ['remote', null, null, 'Runs onRemoteLatency'],
  ] as const)('a %s database with versions %s / %s', async (location, postgres, pgvector, text) => {
    serveHealth([
      () =>
        HttpResponse.json(
          makeHealth({
            database: {
              location,
              postgres_version: postgres,
              pgvector_version: pgvector,
              ...(postgres === null ? { status: 'down', error: 'timeout' } : {}),
            },
          }),
        ),
    ])
    const { user } = renderApp('/settings', { connected: true })
    await waitFor(() => {
      expect(indicator()).toHaveAccessibleName(/^Service status: database (up|down)/)
    })

    await user.click(indicator())

    const database = within(await screen.findByRole('dialog')).getByRole('region', {
      name: 'Database service',
    })
    expect(database).toHaveTextContent(text)
  })

  test('it is never polled', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const queries = serveHealth([() => HttpResponse.json(makeHealth())])
      renderApp('/settings', { connected: true })
      await waitFor(() => {
        expect(queries).toHaveLength(1)
      })

      await vi.advanceTimersByTimeAsync(5 * 60_000)

      expect(queries).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })
})

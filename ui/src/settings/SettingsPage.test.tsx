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

test('outdated documents link to the list filtered to them', async () => {
  const { user } = await openSettings()

  await user.click(within(card('Documents')).getByRole('link', { name: 'Show outdated documents' }))

  expect(screen.getByTestId('location')).toHaveTextContent('/documents?status=outdated')
  expect(await screen.findByLabelText('Status')).toHaveValue('outdated')
})

test('no link when nothing is outdated', async () => {
  server.use(
    http.get(`${API}/admin/settings`, () =>
      HttpResponse.json(
        makeSettings({
          documents: {
            total: 4,
            indexed: 4,
            outdated: { unknown: 0, chunker_changed: 0, embedder_changed: 0 },
          },
        }),
      ),
    ),
  )
  await openSettings()

  expect(card('Documents')).toHaveTextContent('Outdated0')
  expect(
    within(card('Documents')).queryByRole('link', { name: 'Show outdated documents' }),
  ).not.toBeInTheDocument()
})

test('the copilot card names the models and where the summary model comes from', async () => {
  await openSettings()

  const copilot = card('Copilot')
  expect(copilot).toHaveTextContent(
    'Conversation modelLLM_MODELmistralai/mistral-small-3.2-24b-instruct',
  )
  expect(copilot).toHaveTextContent('Summary modelSUMMARY_MODELopenai/gpt-5-mini')
  expect(copilot).not.toHaveTextContent('from LLM_MODEL')
  expect(copilot).toHaveTextContent('Prompts versionPROMPTS_VERSIONdraft-1')
  expect(copilot).toHaveTextContent('Summary prompt versionSUMMARY_PROMPTS_VERSIONsummary-draft-1')
  expect(copilot).toHaveTextContent('Longest summarySUMMARY_MAX_TOKENS800 tokens')
  expect(within(copilot).queryByRole('note')).not.toBeInTheDocument()
})

test('a summary model from LLM_MODEL, and no provider key, are said', async () => {
  const model = 'mistralai/mistral-small-3.2-24b-instruct'
  server.use(
    http.get(`${API}/admin/settings`, () =>
      HttpResponse.json(
        makeSettings({
          copilot: {
            configured: false,
            model,
            summary_model: model,
            summary_model_source: 'llm_model',
            prompts_version: 'draft-1',
            summary_prompts_version: 'summary-draft-1',
            summary_max_tokens: 800,
          },
        }),
      ),
    ),
  )
  await openSettings()

  const copilot = card('Copilot')
  expect(copilot).toHaveTextContent(`Summary modelSUMMARY_MODEL${model}from LLM_MODEL`)
  expect(within(copilot).getByRole('note')).toHaveTextContent('No model provider key')
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

describe('in Spanish', () => {
  async function openSettingsEs() {
    const rendered = renderApp('/settings', { connected: true, language: 'es' })
    await screen.findByRole('region', { name: 'Chunking' })
    return rendered
  }

  test('the cards, their labels and values are Spanish; variables and ids are not', async () => {
    await openSettingsEs()

    expect(screen.getByRole('heading', { name: 'Ajustes de indexación', level: 1 })).toBeVisible()
    expect(window.document.title).toBe('Ajustes de indexación · AYO Admin')
    expect(card('Chunking')).toHaveTextContent('Tamaño de chunkCHUNK_SIZE800 caracteres')
    expect(card('Chunking')).toHaveTextContent('SolapamientoCHUNK_OVERLAP80 caracteres')
    expect(
      within(card('Chunking')).getByRole('button', { name: 'Copiar configuración de chunks' }),
    ).toBeVisible()
    expect(card('Embeddings')).toHaveTextContent(
      'Tamaño de loteEMBEDDING_BATCH_SIZE128 textos por petición',
    )
    expect(card('Subidas')).toHaveTextContent('Archivo más grandeMAX_UPLOAD_BYTES5,0 MB')

    const documents = card('Documentos')
    expect(documents).toHaveTextContent('12 guardados')
    expect(documents).toHaveTextContent('Indexados con la configuración actual9')
    expect(documents).toHaveTextContent(
      'La configuración de chunks ha cambiado desde que se indexó2',
    )
    expect(documents).toHaveTextContent(
      '3 documentos están desactualizados: reprocesa un documento',
    )
    expect(
      within(documents).getByRole('link', { name: 'Ver documentos desactualizados' }),
    ).toBeVisible()

    const copilot = card('Copiloto')
    expect(copilot).toHaveTextContent('Modelo de conversaciónLLM_MODELmistralai/mistral-small')
    expect(copilot).toHaveTextContent('Resumen más largoSUMMARY_MAX_TOKENS800 tokens')
  })

  test('the summary model fallback and a missing key are said in Spanish', async () => {
    server.use(
      http.get(`${API}/admin/settings`, () =>
        HttpResponse.json(
          makeSettings({
            copilot: {
              ...makeSettings().copilot,
              configured: false,
              summary_model_source: 'llm_model',
            },
          }),
        ),
      ),
    )
    await openSettingsEs()

    const copilot = card('Copiloto')
    expect(copilot).toHaveTextContent('de LLM_MODEL')
    expect(within(copilot).getByText('OPENROUTER_API_KEY').tagName).toBe('CODE')
    expect(within(copilot).getByRole('note')).toHaveTextContent(
      'Sin clave del proveedor de modelos (OPENROUTER_API_KEY): no se puede responder a' +
        ' mensajes ni generar resúmenes.',
    )
  })

  test('the status popover is Spanish', async () => {
    server.use(http.get(`${API}/admin/health`, () => HttpResponse.json(makeHealth())))
    const { user } = await openSettingsEs()
    const trigger = screen.getByRole('button', { name: /^Estado del servicio/ })
    await waitFor(() => {
      expect(trigger).toHaveAccessibleName('Estado del servicio: base de datos OK, embeddings OK')
    })

    await user.click(trigger)

    const popover = await screen.findByRole('dialog')
    expect(
      within(popover).getByRole('region', { name: 'Servicio de base de datos' }),
    ).toHaveTextContent(
      'Base de datos: En marchaUbicaciónLocalVersiónPostgreSQL 18.1 · pgvector 0.8.1Latencia3 ms',
    )
    const embeddings = within(popover).getByRole('region', { name: 'Servicio de embeddings' })
    expect(embeddings).toHaveTextContent('Embeddings: En marcha')
    expect(embeddings).toHaveTextContent('Último éxitohace 1 h')
    expect(embeddings).toHaveTextContent('Último errorninguno desde que arrancó la API')
    expect(within(popover).getByRole('button', { name: 'Comprobar ahora' })).toBeVisible()
  })

  test('an unreachable status endpoint says so in Spanish', async () => {
    server.use(http.get(`${API}/admin/health`, () => HttpResponse.error()))
    await openSettingsEs()

    expect(
      await within(card('Servicios')).findByText(/^Estado desconocido: No se puede conectar/),
    ).toBeInTheDocument()
  })
})

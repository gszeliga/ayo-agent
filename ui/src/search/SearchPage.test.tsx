import { act, screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { makeDocument, TENANTS } from '@/test/fixtures/documents'
import { makeHit, makeSearchResponse, QUESTION } from '@/test/fixtures/search'
import { makeHealth } from '@/test/fixtures/services'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

type SearchResponse = components['schemas']['SearchResponse']

const ALL_TENANTS = [...TENANTS, { tenant: 'ayo', document_count: 2, chunk_count: 9 }]

beforeEach(() => {
  server.use(http.get(`${API}/admin/tenants`, () => HttpResponse.json(ALL_TENANTS)))
})

/** Answers every search with `responses` in turn (the last one repeats); records the bodies. */
function answer(...responses: (SearchResponse | (() => Response))[]) {
  const bodies: Record<string, unknown>[] = []
  server.use(
    http.post(`${API}/admin/search`, async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>)
      const next = responses[Math.min(bodies.length, responses.length) - 1] ?? makeSearchResponse()
      return typeof next === 'function' ? next() : HttpResponse.json(next)
    }),
  )
  return bodies
}

async function openSearch(path = '/search') {
  const rendered = renderApp(path, { connected: true })
  await screen.findByRole('heading', { name: 'Test search', level: 1 })
  return rendered
}

const question = () => screen.getByLabelText('Question')
const location = () => screen.getByTestId('location').textContent
const results = () => screen.findByRole('list', { name: 'Results' })
const result = (rank: number) => screen.getByRole('listitem', { name: `Result ${String(rank)}` })

async function ask(user: ReturnType<typeof renderApp>['user'], text = QUESTION) {
  await user.type(question(), text)
  await user.keyboard('{Enter}')
}

test('before the first search: a hint, and the nav entry', async () => {
  await openSearch()

  expect(screen.getByText('Results appear here')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Search' })).toHaveAttribute('aria-current', 'page')
  expect(document.title).toContain('Test search')
})

test('Enter searches with the exact body; the question never reaches the URL', async () => {
  const bodies = answer(makeSearchResponse())
  const { user } = await openSearch('/search?tenant=ayo&k=10')

  await ask(user, `  ${QUESTION}  `)
  await results()

  expect(bodies).toEqual([
    { query: QUESTION, tenants: ['ayo'], top_k: 10, include_outdated: false, debug: true },
  ])
  expect(location()).toBe('/search?tenant=ayo&k=10')
  expect(location()).not.toContain('junta')
})

test('Shift+Enter adds a line, and typing sends nothing', async () => {
  const bodies = answer()
  const { user } = await openSearch()

  await user.type(question(), 'primera{Shift>}{Enter}{/Shift}segunda')

  expect(question()).toHaveValue('primera\nsegunda')
  expect(bodies).toEqual([])
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await results()
  expect(bodies[0]).toMatchObject({ query: 'primera\nsegunda' })
})

test('the form checks the limits before sending', async () => {
  const bodies = answer()
  const { user } = await openSearch()

  await user.click(screen.getByRole('button', { name: 'Search' }))
  expect(screen.getByText('Type a question.')).toBeInTheDocument()
  expect(question()).toHaveAttribute('aria-invalid', 'true')

  await user.type(question(), 'x')
  const topK = screen.getByLabelText('Top k')
  await user.clear(topK)
  await user.type(topK, '51')
  await user.keyboard('{Enter}')
  expect(screen.getByText('Top k: A whole number from 1 to 50.')).toBeInTheDocument()

  await user.clear(topK)
  await user.type(topK, '5')
  await user.click(screen.getByRole('button', { name: 'Options' }))
  await user.type(screen.getByLabelText('Minimum similarity'), '1,5')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  // The options open, so the error shows next to its field.
  expect(await screen.findByText('A number from 0 to 1, or empty for none.')).toBeInTheDocument()

  expect(bodies).toEqual([])
})

test('the options button says how many are set', async () => {
  await openSearch('/search?min=0.2&outdated=1')

  expect(screen.getByRole('button', { name: 'Options, 2 set' })).toBeInTheDocument()
})

test('an over-long question is refused, with the count', async () => {
  const bodies = answer()
  const { user } = await openSearch()

  await user.click(question())
  await user.paste('a'.repeat(2001))
  expect(screen.getByText('2001 / 2000')).toBeInTheDocument()
  await user.keyboard('{Enter}')

  expect(screen.getByText('At most 2000 characters (now 2001).')).toBeInTheDocument()
  expect(bodies).toEqual([])
})

test('results: rank, similarity, document, where, text', async () => {
  answer(makeSearchResponse())
  const { user } = await openSearch()
  await ask(user)
  await results()

  const first = result(1)
  expect(first).toHaveTextContent('#1')
  expect(first).toHaveTextContent('Similarity 0.8734')
  expect(first).toHaveTextContent('planta-norte')
  expect(first).toHaveTextContent('PRO-014 Control de sellado > 3. Pasos')
  expect(first).toHaveTextContent('pro-014-control-sellado.md · chunk 2')
  expect(within(first).getByRole('link', { name: 'PRO-014 Control de sellado' })).toHaveAttribute(
    'href',
    '/documents/upload-3f9a1c2b7d4e?tab=chunks',
  )
  expect(within(first).queryByText('Other model')).not.toBeInTheDocument()
  const more = within(first).getByRole('button', { name: 'Show more' })
  expect(more).toHaveAttribute('aria-expanded', 'false')
  await user.click(more)
  expect(within(first).getByRole('button', { name: 'Show less' })).toHaveAttribute(
    'aria-expanded',
    'true',
  )

  const second = result(2)
  // No title: the file name. Chunk 23 is on the second page of 20.
  expect(within(second).getByRole('link', { name: 'man-102-bomba-centrifuga.md' })).toHaveAttribute(
    'href',
    '/documents/upload-a1b2c3d4e5f6?tab=chunks&cpage=2',
  )
  expect(second).toHaveTextContent('Before the first heading')
  expect(within(second).getByText('Other model')).toBeInTheDocument()
  expect(within(second).queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
})

test('the summary: count, scope, timings, and the details on request', async () => {
  answer(makeSearchResponse())
  const { user } = await openSearch('/search?min=0.2&outdated=1')
  await ask(user)
  await results()

  const summary = screen.getByRole('status', { name: 'Search summary' })
  expect(summary).toHaveTextContent('2 results')
  expect(summary).toHaveTextContent('top 5 · min 0.2 · all tenants · other models included')
  expect(summary).toHaveTextContent('Embedding 41.2 ms · Search 6.3 ms · Total 47.5 ms')
  expect(screen.queryByText('voyage-4/document/1024')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Details' }))

  expect(screen.getByText('voyage-4/document/1024')).toBeInTheDocument()
  expect(screen.getByText('Embedded query (input_type: query)')).toBeInTheDocument()
})

test('tenants are picked from the list with their counts', async () => {
  const bodies = answer(makeSearchResponse())
  const { user } = await openSearch()

  await user.click(screen.getByRole('button', { name: /Tenants All tenants/ }))
  await user.click(await screen.findByRole('checkbox', { name: /planta-norte\s*2 docs · 60 ch/ }))
  await user.click(screen.getByRole('checkbox', { name: /ayo/ }))
  await user.keyboard('{Escape}')
  expect(screen.getByRole('button', { name: 'Tenants ayo + planta-norte' })).toBeInTheDocument()
  await ask(user)
  await results()

  expect(bodies[0]).toMatchObject({ tenants: ['ayo', 'planta-norte'] })
  expect(location()).toBe('/search?tenant=ayo&tenant=planta-norte')
})

test('skipped documents: a banner to include them or review them', async () => {
  const bodies = answer(
    makeSearchResponse({ skipped: { embedder_mismatch: 2 } }),
    makeSearchResponse({ results: [makeHit({ embedder_outdated: true })] }),
  )
  const { user } = await openSearch()
  await ask(user)
  await results()

  expect(screen.getByText(/2 documents were left out/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Review outdated documents' })).toHaveAttribute(
    'href',
    '/documents?status=outdated',
  )
  await user.click(screen.getByRole('button', { name: 'Include them' }))

  await waitFor(() => {
    expect(bodies).toHaveLength(2)
  })
  expect(bodies[1]).toMatchObject({ query: QUESTION, include_outdated: true })
  expect(await screen.findByText('1 result')).toBeInTheDocument()
  expect(screen.queryByText(/left out/)).not.toBeInTheDocument()
  expect(location()).toBe('/search?outdated=1')
})

test('nothing reached the minimum: clear it and search again', async () => {
  const bodies = answer(makeSearchResponse({ results: [] }), makeSearchResponse())
  const { user } = await openSearch('/search?min=0.9')
  await ask(user)

  expect(await screen.findByText('Nothing reached the minimum similarity')).toBeInTheDocument()
  expect(screen.getByText('None of the top 5 chunks scored 0.9 or more.')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Clear the minimum and search again' }))

  await results()
  expect(bodies[0]).toMatchObject({ min_similarity: 0.9 })
  expect(bodies[1]).not.toHaveProperty('min_similarity')
  expect(location()).toBe('/search')
})

test.each([
  ['/search', { embedder_mismatch: 0 }, 'Nothing to search', 'The knowledge base is empty'],
  ['/search?tenant=ayo', { embedder_mismatch: 0 }, 'Nothing to search', 'These tenants have no'],
  ['/search', { embedder_mismatch: 3 }, 'No searchable documents', 'Every matching document'],
])('no results on %s with %j: %s', async (path, skipped, title, description) => {
  answer(makeSearchResponse({ results: [], skipped }))
  const { user } = await openSearch(path)
  await ask(user)

  expect(await screen.findByText(title)).toBeInTheDocument()
  expect(screen.getByText(new RegExp(description))).toBeInTheDocument()
})

test('a 422 shows next to its field', async () => {
  answer(() =>
    HttpResponse.json(
      {
        detail: [
          {
            type: 'string_too_long',
            loc: ['body', 'query'],
            msg: 'String should have at most 2000 characters',
          },
        ],
      },
      { status: 422 },
    ),
  )
  const { user } = await openSearch()
  await ask(user)

  expect(await screen.findByText('String should have at most 2000 characters')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()

  // Editing the question clears it.
  await user.type(question(), '?')
  expect(screen.queryByText('String should have at most 2000 characters')).not.toBeInTheDocument()
})

test('a 502 says nothing was searched; Retry searches again', async () => {
  const bodies = answer(
    () =>
      HttpResponse.json(
        { detail: [{ type: 'embedding_failed', loc: [], msg: 'embedding provider failed' }] },
        { status: 502 },
      ),
    makeSearchResponse(),
  )
  const { user } = await openSearch()
  await ask(user)

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('The embedding provider failed')
  expect(alert).toHaveTextContent('nothing was searched')
  await user.click(within(alert).getByRole('button', { name: 'Retry' }))

  await results()
  expect(bodies).toHaveLength(2)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('an unreachable API is said so', async () => {
  answer(() => HttpResponse.error())
  const { user } = await openSearch()
  await ask(user)

  expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the API at")
})

test('a 401 returns to the connect screen', async () => {
  answer(() =>
    HttpResponse.json(
      { detail: [{ type: 'invalid_api_key', loc: ['header', 'X-API-Key'], msg: 'invalid key' }] },
      { status: 401 },
    ),
  )
  const { user } = await openSearch()
  await ask(user)

  await waitFor(() => {
    expect(location()).toBe('/connect?next=%2Fsearch')
  })
})

test('the button waits while a search runs', async () => {
  const bodies: unknown[] = []
  server.use(
    http.post(`${API}/admin/search`, async ({ request }) => {
      bodies.push(await request.json())
      await delay(50)
      return HttpResponse.json(makeSearchResponse())
    }),
  )
  const { user } = await openSearch()
  await ask(user)

  expect(screen.getByRole('button', { name: 'Searching…' })).toBeDisabled()
  await user.keyboard('{Enter}')
  await results()
  expect(bodies).toHaveLength(1)
})

test('a provider outage is announced before searching', async () => {
  server.use(
    http.get(`${API}/admin/health`, () =>
      HttpResponse.json(makeHealth({ embeddings: { status: 'down', error: 'HTTP 503' } })),
    ),
  )
  await openSearch()

  expect(await screen.findByText(/searches fail until it is back \(HTTP 503\)/)).toBeInTheDocument()
})

test('a result opens its chunk, and Back to search keeps the results', async () => {
  const bodies = answer(makeSearchResponse())
  const doc = makeDocument({ doc_id: 'upload-3f9a1c2b7d4e', chunk_count: 3 })
  server.use(
    http.get(`${API}/admin/documents/${doc.doc_id}`, () => HttpResponse.json(doc)),
    http.get(`${API}/admin/documents/${doc.doc_id}/chunks`, () =>
      HttpResponse.json({
        items: [0, 1, 2].map((i) => ({
          chunk_index: i,
          heading: 'PRO-014 Control de sellado > 3. Pasos',
          chunk_text: `Paso ${String(i)}`,
          char_count: 6,
          embedding: null,
        })),
        total: 3,
        limit: 20,
        offset: 0,
      }),
    ),
  )
  const { user } = await openSearch('/search?k=3')
  await ask(user)
  await results()

  await user.click(within(result(1)).getByRole('link', { name: 'PRO-014 Control de sellado' }))

  const chunk = await screen.findByRole('article', { name: 'Chunk 2' })
  expect(chunk).toHaveAttribute('data-highlighted', 'true')
  expect(within(chunk).getByText('From the search')).toBeInTheDocument()
  expect(screen.getByRole('article', { name: 'Chunk 1' })).not.toHaveAttribute('data-highlighted')
  expect(location()).toBe('/documents/upload-3f9a1c2b7d4e?tab=chunks')

  await user.click(within(screen.getByRole('main')).getByRole('link', { name: 'Search' }))

  expect(location()).toBe('/search?k=3')
  await results()
  expect(question()).toHaveValue(QUESTION)
  expect(bodies).toHaveLength(1)
})

describe('in Spanish', () => {
  async function openSearchEs(path = '/search') {
    const rendered = renderApp(path, { connected: true, language: 'es' })
    await screen.findByRole('heading', { name: 'Búsqueda de prueba', level: 1 })
    return rendered
  }
  const pregunta = () => screen.getByLabelText('Pregunta')
  async function askEs(user: ReturnType<typeof renderApp>['user']) {
    await user.type(pregunta(), QUESTION)
    await user.keyboard('{Enter}')
  }

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('the form, its hint and the first-visit state are Spanish', async () => {
    await openSearchEs()

    expect(document.title).toBe('Búsqueda de prueba · AYO Admin')
    expect(screen.getByText('Los resultados aparecen aquí')).toBeInTheDocument()
    expect(pregunta()).toHaveAccessibleDescription(/^Enter busca, Mayús\+Enter añade una línea/)
    // The placeholder is an example question in the content's language, in any UI language.
    expect(pregunta()).toHaveAttribute(
      'placeholder',
      '¿Qué hago si la junta de la bomba pierde presión?',
    )
    expect(screen.getByRole('button', { name: 'Buscar' })).toBeInTheDocument()
  })

  test('the local checks are Spanish, with the count', async () => {
    answer()
    const { user } = await openSearchEs()

    await user.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(screen.getByText('Escribe una pregunta.')).toBeInTheDocument()
    await user.click(pregunta())
    await user.paste('a'.repeat(2001))
    await user.keyboard('{Enter}')
    expect(screen.getByText('Como máximo 2000 caracteres (ahora 2001).')).toBeInTheDocument()

    await user.clear(pregunta())
    await user.type(pregunta(), 'x')
    const topK = screen.getByLabelText('Top k')
    await user.clear(topK)
    await user.type(topK, '51')
    await user.keyboard('{Enter}')
    expect(screen.getByText('Top k: Un número entero del 1 al 50.')).toBeInTheDocument()
  })

  test('the organization picker and the options are Spanish', async () => {
    const { user } = await openSearchEs()

    await user.click(
      screen.getByRole('button', { name: 'Organizaciones Todas las organizaciones' }),
    )
    const picker = await screen.findByRole('dialog', { name: 'Organizaciones en las que buscar' })
    expect(
      within(picker).getByRole('checkbox', { name: /planta-norte\s*2 docs · 60 ch/ }),
    ).toBeVisible()
    expect(picker).toHaveTextContent('la organización compartida ayo, nunca entre clientes')
    await user.keyboard('{Escape}')

    await user.click(screen.getByRole('button', { name: 'Opciones' }))
    const options = await screen.findByRole('dialog', { name: 'Opciones de búsqueda' })
    expect(within(options).getByLabelText('Similitud mínima')).toHaveAccessibleDescription(
      /^De 0 a 1\./,
    )
    await user.click(
      within(options).getByLabelText(/^Incluir documentos con embeddings de otro modelo/),
    )
    await user.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: 'Opciones, 1 activa' })).toBeInTheDocument()
  })

  test('results and the summary are Spanish, with decimal commas', async () => {
    answer(makeSearchResponse())
    const { user } = await openSearchEs('/search?min=0.2')
    await askEs(user)
    const list = await screen.findByRole('list', { name: 'Resultados' })

    const first = within(list).getByRole('listitem', { name: 'Resultado 1' })
    expect(first).toHaveTextContent('Similitud 0,8734')
    expect(first).toHaveTextContent('pro-014-control-sellado.md · chunk 2')
    expect(within(first).getByRole('button', { name: 'Mostrar más' })).toBeVisible()
    const second = within(list).getByRole('listitem', { name: 'Resultado 2' })
    expect(second).toHaveTextContent('Antes del primer encabezado')
    expect(within(second).getByText('Otro modelo')).toBeInTheDocument()

    const summary = screen.getByRole('status', { name: 'Resumen de la búsqueda' })
    expect(summary).toHaveTextContent('2 resultados')
    expect(summary).toHaveTextContent('top 5 · mín. 0,2 · todas las organizaciones')
    expect(summary).toHaveTextContent('Embedding 41,2 ms · Búsqueda 6,3 ms · Total 47,5 ms')
    await user.click(screen.getByRole('button', { name: 'Detalles' }))
    expect(
      screen.getByText('Consulta convertida en embedding (input_type: query)'),
    ).toBeInTheDocument()
  })

  test('the skipped banner and the empty states are Spanish', async () => {
    answer(
      makeSearchResponse({ skipped: { embedder_mismatch: 1 } }),
      makeSearchResponse({ results: [], skipped: { embedder_mismatch: 0 } }),
    )
    const { user } = await openSearchEs()
    await askEs(user)
    await screen.findByRole('list', { name: 'Resultados' })

    expect(screen.getByText(/^1 documento se ha quedado fuera/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Incluirlos' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Revisar documentos desactualizados' })).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Incluirlos' }))
    expect(await screen.findByText('Nada en lo que buscar')).toBeInTheDocument()
    expect(
      screen.getByText('La base de conocimiento está vacía: sube un documento primero.'),
    ).toBeInTheDocument()
  })

  test('nothing above the minimum says so in Spanish', async () => {
    answer(makeSearchResponse({ results: [] }))
    const { user } = await openSearchEs('/search?min=0.9')
    await askEs(user)

    expect(await screen.findByText('Nada ha alcanzado la similitud mínima')).toBeInTheDocument()
    expect(
      screen.getByText('Ninguno de los 5 primeros chunks ha llegado a 0,9.'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Quitar el mínimo y volver a buscar' }),
    ).toBeInTheDocument()
  })

  test('a 422 is placed as received; a 502 is worded, and rewords on a switch', async () => {
    answer(
      () =>
        HttpResponse.json(
          { detail: [{ type: 'too_long', loc: ['body', 'query'], msg: 'String too long' }] },
          { status: 422 },
        ),
      () =>
        HttpResponse.json(
          { detail: [{ type: 'embedding_failed', loc: [], msg: 'provider failed' }] },
          { status: 502 },
        ),
    )
    let browser = ['es-ES']
    vi.spyOn(navigator, 'languages', 'get').mockImplementation(() => browser)
    const { user } = renderApp('/search', { connected: true })
    await screen.findByRole('heading', { name: 'Búsqueda de prueba', level: 1 })
    await askEs(user)
    expect(await screen.findByText('String too long')).toBeInTheDocument()

    await user.type(pregunta(), '?')
    await user.keyboard('{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /^El proveedor de embeddings ha fallado: no se ha podido convertir la pregunta/,
    )

    browser = ['en-GB']
    act(() => {
      window.dispatchEvent(new Event('languagechange'))
    })
    expect(screen.getByRole('alert')).toHaveTextContent(
      /^The embedding provider failed: the question could not be embedded/,
    )
  })
})

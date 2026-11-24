import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { CASES, makeCaseDetail, makeCaseItem } from '@/test/fixtures/cases'
import { TENANTS } from '@/test/fixtures/documents'
import { API, KEY, renderApp } from '@/test/render'
import { server } from '@/test/server'

type CaseListItem = components['schemas']['CaseListItem']

/** Stands in for `list_cases`: filters, pages by limit/offset, records each query. */
function serve(cases: CaseListItem[] = CASES) {
  const queries: URLSearchParams[] = []
  server.use(
    http.get(`${API}/admin/cases`, ({ request }) => {
      const query = new URL(request.url).searchParams
      queries.push(query)
      const tenant = query.get('tenant')
      const phase = query.get('phase')
      const closed = query.get('closed')
      const q = query.get('q')?.toLowerCase()
      const matching = cases.filter(
        (item) =>
          (!tenant || item.tenant === tenant) &&
          (!phase || item.phase === phase) &&
          (closed === null || (item.closed_at !== null) === (closed === 'true')) &&
          (!q || (item.title ?? '').toLowerCase().includes(q)),
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
    // An opened case: its detail, no turns (the case view has its own tests).
    http.get(`${API}/admin/cases/:caseId`, ({ params }) => {
      const item = cases.find((c) => c.case_id === params.caseId)
      return item
        ? HttpResponse.json(makeCaseDetail(item, { turns: 0 }))
        : HttpResponse.json(
            { detail: [{ type: 'case_not_found', loc: ['path', 'case_id'], msg: 'No case.' }] },
            { status: 404 },
          )
    }),
    http.get(`${API}/admin/cases/:caseId/turns`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
    ),
  )
  return queries
}

const location = () => screen.getByTestId('location').textContent
const caseList = () => screen.findByRole('list', { name: 'Cases' })
const rows = async () => within(await caseList()).getAllByRole('link')
const last = (queries: URLSearchParams[]) => Object.fromEntries(queries.at(-1) ?? [])

function manyCases(count: number): CaseListItem[] {
  return Array.from({ length: count }, (_, i) =>
    makeCaseItem({ title: `Caso ${String(i + 1).padStart(2, '0')}`, hoursAgo: i + 1 }),
  )
}

test('the navigation puts the test chat first, then the knowledge pages', async () => {
  serve()
  renderApp('/chat', { connected: true })

  const nav = screen.getByRole('navigation', { name: 'Main' })
  const links = within(nav).getAllByRole('link')
  expect(links.map((link) => link.textContent)).toEqual([
    'Test chat',
    'Documents',
    'Search',
    'Indexing settings',
  ])
  expect(within(nav).getByRole('group', { name: 'Knowledge' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Test chat' })).toHaveAttribute('aria-current', 'page')
  expect(await screen.findByRole('heading', { name: 'Pick a case' })).toBeInTheDocument()
  expect(document.title).toBe('Test chat · AYO Admin')
})

test('connecting still lands on the documents', async () => {
  const { user } = renderApp('/connect')
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/documents`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 25, offset: 0 }),
    ),
  )

  await user.clear(screen.getByLabelText('API address'))
  await user.type(screen.getByLabelText('API address'), API)
  await user.type(screen.getByLabelText('Admin key'), KEY)
  await user.click(screen.getByRole('button', { name: 'Connect' }))

  await waitFor(() => {
    expect(location()).toBe('/documents')
  })
})

test('a link to a case survives the connect screen', async () => {
  serve()
  const caseId = CASES[1]?.case_id ?? ''
  const { user } = renderApp(`/chat/${caseId}`)

  expect(location()).toBe(`/connect?next=${encodeURIComponent(`/chat/${caseId}`)}`)
  await user.clear(screen.getByLabelText('API address'))
  await user.type(screen.getByLabelText('API address'), API)
  await user.type(screen.getByLabelText('Admin key'), KEY)
  await user.click(screen.getByRole('button', { name: 'Connect' }))

  await waitFor(() => {
    expect(location()).toBe(`/chat/${caseId}`)
  })
  const selected = (await rows()).find((row) => row.getAttribute('aria-current') === 'page')
  expect(selected).toHaveTextContent('Paradas repetidas de la llenadora L3')
})

test('rows show what the API returns', async () => {
  const queries = serve()
  renderApp('/chat', { connected: true })

  const [open, action, closed, other, untitled] = await rows()
  expect(screen.getByRole('heading', { name: /Cases/ })).toHaveTextContent('Cases5')
  expect(last(queries)).toEqual({ limit: '20', offset: '0' })

  expect(open).toHaveTextContent('Merma del 4 % en el envasado de la línea 2')
  expect(open).toHaveTextContent('Analyse')
  expect(open).toHaveTextContent('cliente-acme')
  expect(open).toHaveTextContent('9 turns')
  expect(open).toHaveTextContent('Updated 1 h ago')
  expect(open).not.toHaveTextContent('pending')
  expect(open).not.toHaveTextContent('overdue')
  expect(open).not.toHaveTextContent('Other channel')
  expect(open).toHaveAttribute('href', `/chat/${CASES[0]?.case_id ?? ''}`)

  expect(action).toHaveTextContent('Action')
  expect(action).toHaveTextContent('3 pending')
  expect(action).toHaveTextContent('1 overdue')

  expect(closed).toHaveTextContent('Closed')
  expect(other).toHaveTextContent('Other channel')
  expect(untitled).toHaveTextContent('Untitled case')
  expect(untitled).toHaveTextContent('1 turn')
  expect(untitled).not.toHaveTextContent('1 turns')
})

test('the overdue badge is the API value, never recomputed', async () => {
  // Pending actions but none overdue per the API: no badge, whatever the dates.
  serve([makeCaseItem({ pending_actions: 4, overdue_actions: 0 })])
  renderApp('/chat', { connected: true })

  const [row] = await rows()
  expect(row).toHaveTextContent('4 pending')
  expect(row).not.toHaveTextContent('overdue')
})

test('selecting a row opens its case and marks it', async () => {
  serve()
  const { user } = renderApp('/chat', { connected: true })

  const [, action] = await rows()
  if (!action) throw new Error('no row')
  await user.click(action)

  await waitFor(() => {
    expect(location()).toBe(`/chat/${CASES[1]?.case_id ?? ''}`)
  })
  expect(action).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: 'Test chat' })).toHaveAttribute('aria-current', 'page')
})

test('each filter goes to the API, and they combine', async () => {
  const queries = serve()
  const { user } = renderApp('/chat', { connected: true })
  await rows()

  await user.selectOptions(await screen.findByRole('combobox', { name: 'Tenant' }), 'planta-norte')
  await waitFor(() => {
    expect(last(queries)).toEqual({ tenant: 'planta-norte', limit: '20', offset: '0' })
  })
  expect(await rows()).toHaveLength(1)

  await user.selectOptions(screen.getByRole('combobox', { name: 'Phase' }), 'Action')
  await waitFor(() => {
    expect(last(queries)).toMatchObject({ tenant: 'planta-norte', phase: 'action' })
  })

  await user.selectOptions(screen.getByRole('combobox', { name: 'Tenant' }), '')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Phase' }), '')
  const state = screen.getByRole('group', { name: 'State' })
  await user.click(within(state).getByRole('button', { name: 'Closed' }))
  await waitFor(() => {
    expect(last(queries)).toEqual({ closed: 'true', limit: '20', offset: '0' })
  })
  expect(within(state).getByRole('button', { name: 'Closed' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await waitFor(async () => {
    expect(await rows()).toHaveLength(1)
  })

  await user.click(within(state).getByRole('button', { name: 'Open' }))
  await waitFor(() => {
    expect(last(queries)).toEqual({ closed: 'false', limit: '20', offset: '0' })
  })
  await waitFor(async () => {
    expect(await rows()).toHaveLength(4)
  })
})

test('the search waits for typing to pause and never reaches the URL', async () => {
  const queries = serve()
  const { user } = renderApp('/chat', { connected: true })
  await rows()

  await user.type(screen.getByRole('searchbox', { name: 'Search cases' }), '  bomba ')

  await waitFor(() => {
    expect(last(queries)).toEqual({ q: 'bomba', limit: '20', offset: '0' })
  })
  // One request for the list, one for the whole search: none per keystroke.
  expect(queries).toHaveLength(2)
  expect(await rows()).toHaveLength(1)
  expect(location()).toBe('/chat')
})

test('Load more fetches the next page and goes away at the end', async () => {
  const queries = serve(manyCases(25))
  const { user } = renderApp('/chat', { connected: true })

  expect(await rows()).toHaveLength(20)
  await user.click(screen.getByRole('button', { name: 'Load more' }))

  await waitFor(async () => {
    expect(await rows()).toHaveLength(25)
  })
  expect(last(queries)).toEqual({ limit: '20', offset: '20' })
  expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
})

test('a case seen on two pages is listed once', async () => {
  const cases = manyCases(25)
  let calls = 0
  server.use(
    http.get(`${API}/admin/cases`, ({ request }) => {
      calls += 1
      const offset = Number(new URL(request.url).searchParams.get('offset'))
      // Between the two pages the 20th case moved down one place.
      const items = offset === 0 ? cases.slice(0, 20) : cases.slice(19, 25)
      return HttpResponse.json({ items, total: 25, limit: 20, offset })
    }),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
  )
  const { user } = renderApp('/chat', { connected: true })

  await rows()
  await user.click(screen.getByRole('button', { name: 'Load more' }))

  await waitFor(() => {
    expect(calls).toBe(2)
  })
  await waitFor(async () => {
    expect(await rows()).toHaveLength(25)
  })
})

test('no cases at all says so, without a clear button', async () => {
  serve([])
  renderApp('/chat', { connected: true })

  expect(await screen.findByRole('heading', { name: 'No conversations yet' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
})

test('no match offers to clear the filters', async () => {
  const queries = serve()
  const { user } = renderApp('/chat', { connected: true })
  await rows()

  await user.type(screen.getByRole('searchbox', { name: 'Search cases' }), 'nada parecido')
  expect(await screen.findByRole('heading', { name: 'No cases match' })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Clear filters' }))

  expect(await rows()).toHaveLength(5)
  expect(screen.getByRole('searchbox', { name: 'Search cases' })).toHaveValue('')
  // The unfiltered list comes back from the cache: no new request.
  expect(queries.map((query) => query.get('q'))).toEqual([null, 'nada parecido'])
})

test('a failed load says so and Retry asks again', async () => {
  let fail = true
  server.use(
    http.get(`${API}/admin/cases`, () =>
      fail
        ? HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'Internal error.' }] },
            { status: 500 },
          )
        : HttpResponse.json({ items: CASES, total: CASES.length, limit: 20, offset: 0 }),
    ),
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
  )
  const { user } = renderApp('/chat', { connected: true })

  const alert = await screen.findByRole('alert')
  fail = false
  await user.click(within(alert).getByRole('button', { name: 'Retry' }))

  expect(await rows()).toHaveLength(5)
})

test('the list collapses to a rail with the count, and comes back as it was', async () => {
  const queries = serve()
  const { user } = renderApp('/chat', { connected: true })
  await rows()
  await user.click(
    within(screen.getByRole('group', { name: 'State' })).getByRole('button', {
      name: 'Open',
    }),
  )
  await waitFor(async () => {
    expect(await rows()).toHaveLength(4)
  })
  const asked = queries.length

  await user.click(screen.getByRole('button', { name: 'Hide cases' }))

  expect(screen.queryByRole('list', { name: 'Cases' })).not.toBeInTheDocument()
  expect(screen.getByRole('complementary', { name: 'Cases list' })).toHaveTextContent('4 cases')

  await user.click(screen.getByRole('button', { name: 'Show cases' }))

  expect(await rows()).toHaveLength(4)
  expect(
    within(screen.getByRole('group', { name: 'State' })).getByRole('button', {
      name: 'Open',
    }),
  ).toHaveAttribute('aria-pressed', 'true')
  expect(queries).toHaveLength(asked)
})

test('switching cases keeps the filters and the loaded rows', async () => {
  const queries = serve(manyCases(25))
  const { user } = renderApp('/chat', { connected: true })
  await rows()
  await user.click(screen.getByRole('button', { name: 'Load more' }))
  await waitFor(async () => {
    expect(await rows()).toHaveLength(25)
  })
  const asked = queries.length

  const all = await rows()
  await user.click(all[22] ?? all[0] ?? document.body)
  await user.click((await rows())[3] ?? document.body)

  expect(await rows()).toHaveLength(25)
  expect(queries).toHaveLength(asked)
})

describe('in Spanish', () => {
  test('the page, the filters and the rows are Spanish', async () => {
    const queries = serve()
    const { user } = renderApp('/chat', { connected: true, language: 'es' })

    expect(await screen.findByRole('heading', { name: 'Elige un caso' })).toBeInTheDocument()
    expect(document.title).toBe('Chat de prueba · AYO Admin')
    const list = await screen.findByRole('list', { name: 'Casos' })
    const [open, action, closed, other, untitled] = within(list).getAllByRole('link')
    expect(screen.getByRole('heading', { name: /Casos/ })).toHaveTextContent('Casos5')

    expect(open).toHaveTextContent('Analizar')
    expect(open).toHaveTextContent('9 turnos')
    expect(open).toHaveTextContent('Actualizado hace 1 h')
    expect(action).toHaveTextContent('Actuar')
    expect(action).toHaveTextContent('3 pendientes')
    expect(action).toHaveTextContent('1 atrasada')
    expect(closed).toHaveTextContent('Cerrado')
    expect(other).toHaveTextContent('Otro canal')
    expect(untitled).toHaveTextContent('Caso sin título')
    expect(untitled).toHaveTextContent('1 turno')
    expect(untitled).not.toHaveTextContent('1 turnos')

    expect(screen.getByRole('searchbox', { name: 'Buscar casos' })).toHaveAttribute(
      'placeholder',
      'Busca qué ocurre',
    )
    const tenant = screen.getByRole('combobox', { name: 'Organización' })
    expect(within(tenant).getByRole('option', { name: 'Todas las organizaciones' })).toBeVisible()
    const phase = screen.getByRole('combobox', { name: 'Fase' })
    expect(
      within(phase)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual([
      'Todas las fases',
      'Entender',
      'Cuestionar',
      'Analizar',
      'Actuar',
      'Seguimiento',
      'Cerrado',
    ])
    // The values stay the API's.
    await user.selectOptions(phase, 'Seguimiento')
    await waitFor(() => {
      expect(last(queries)).toMatchObject({ phase: 'followup' })
    })
    const state = screen.getByRole('group', { name: 'Estado' })
    expect(
      within(state)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Todos', 'Abiertos', 'Cerrados'])
    expect(
      screen.getByRole('separator', { name: 'Cambiar el ancho de la lista de casos' }),
    ).toHaveAttribute('aria-valuetext', expect.stringMatching(/^\d+ píxeles de ancho$/))
  })

  test('no match and no cases are Spanish', async () => {
    serve()
    const { user } = renderApp('/chat', { connected: true, language: 'es' })
    await screen.findByRole('list', { name: 'Casos' })

    await user.type(screen.getByRole('searchbox', { name: 'Buscar casos' }), 'nada parecido')
    expect(await screen.findByRole('heading', { name: 'Ningún caso coincide' })).toBeInTheDocument()
    expect(screen.getByText('Prueba otra búsqueda u otro filtro.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Quitar filtros' }))
    expect(await screen.findByRole('list', { name: 'Casos' })).toBeInTheDocument()

    serve([])
    renderApp('/chat', { connected: true, language: 'es' })
    expect(
      await screen.findByRole('heading', { name: 'Aún no hay conversaciones' }),
    ).toBeInTheDocument()
  })

  test('Load more and the collapsed rail are Spanish', async () => {
    serve(manyCases(25))
    const { user } = renderApp('/chat', { connected: true, language: 'es' })
    await screen.findByRole('list', { name: 'Casos' })
    expect(screen.getByRole('button', { name: 'Cargar más' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ocultar casos' }))

    const rail = screen.getByRole('group', { name: 'Lista de casos (contraída)' })
    expect(rail).toHaveTextContent('25 casos')
    expect(within(rail).getByRole('button', { name: 'Nueva conversación' })).toBeInTheDocument()
    await user.click(within(rail).getByRole('button', { name: 'Mostrar casos' }))
    expect(await screen.findByRole('list', { name: 'Casos' })).toBeInTheDocument()
  })

  test('a new conversation is Spanish, from the dialog to the empty chat', async () => {
    serve()
    const { user } = renderApp('/chat/new', { connected: true, language: 'es' })

    expect(
      await screen.findByRole('heading', { name: 'Empieza una conversación nueva' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Elige la organización; el primer mensaje abre el caso.'),
    ).toBeInTheDocument()

    await user.click(
      screen.getAllByRole('button', { name: 'Nueva conversación' })[0] ?? document.body,
    )
    const dialog = await screen.findByRole('dialog', { name: 'Nueva conversación' })
    expect(dialog).toHaveTextContent('El primer mensaje crea el caso, para esta organización.')
    expect(await within(dialog).findByLabelText('Organización')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Cancelar' })).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Empezar' }))

    expect(
      await screen.findByRole('heading', { name: 'Nueva conversación', level: 1 }),
    ).toBeVisible()
    expect(
      within(screen.getByRole('log', { name: 'Conversación' })).getByText(
        'Envía el primer mensaje para abrir un caso.',
      ),
    ).toBeInTheDocument()
  })

  test('the dialog says when there are no organizations yet', async () => {
    serve()
    server.use(http.get(`${API}/admin/tenants`, () => HttpResponse.json([])))
    const { user } = renderApp('/chat', { connected: true, language: 'es' })
    await screen.findByRole('list', { name: 'Casos' })

    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva conversación' })
    expect(
      await within(dialog).findByText(
        'Aún no hay organizaciones: una aparece en cuanto tiene un documento.',
      ),
    ).toBeInTheDocument()
  })
})

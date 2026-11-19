import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { CASES, makeCaseDetail, makeCaseItem, makeTurn } from '@/test/fixtures/cases'
import { TENANTS } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

type CaseDetail = components['schemas']['CaseDetail']
type CaseTurn = components['schemas']['CaseTurn']

interface Served {
  detail: CaseDetail
  turns: CaseTurn[]
}

/** Stands in for the cases API: the list, each case and its turns; records the turn queries. */
function serve(cases: Served[]) {
  const turnQueries: { offset: string | null; limit: string | null }[] = []
  let detailCalls = 0
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/cases`, () =>
      HttpResponse.json({ items: CASES, total: CASES.length, limit: 20, offset: 0 }),
    ),
    http.get(`${API}/admin/cases/:caseId`, ({ params }) => {
      detailCalls += 1
      const found = cases.find((c) => c.detail.case_id === params.caseId)
      return found
        ? HttpResponse.json(found.detail)
        : HttpResponse.json(
            { detail: [{ type: 'case_not_found', loc: ['path', 'case_id'], msg: 'No case.' }] },
            { status: 404 },
          )
    }),
    http.get(`${API}/admin/cases/:caseId/turns`, ({ params, request }) => {
      const query = new URL(request.url).searchParams
      turnQueries.push({ offset: query.get('offset'), limit: query.get('limit') })
      const found = cases.find((c) => c.detail.case_id === params.caseId)
      const turns = found?.turns ?? []
      const offset = Number(query.get('offset'))
      const limit = Number(query.get('limit'))
      return HttpResponse.json({
        items: turns.slice(offset, offset + limit),
        total: turns.length,
        limit,
        offset,
      })
    }),
  )
  return { turnQueries, detailCalls: () => detailCalls }
}

function turnsFor(count: number): CaseTurn[] {
  return Array.from({ length: count }, (_, i) => makeTurn(i + 1))
}

function openCase(index = 0, overrides: Partial<CaseDetail> = {}, turns?: CaseTurn[]): Served {
  const item = CASES[index] ?? makeCaseItem()
  const detail = makeCaseDetail(item, overrides)
  return { detail, turns: turns ?? turnsFor(detail.turns) }
}

const log = () => screen.findByRole('log', { name: 'Conversation' })
const turnItems = async () => within(await log()).findAllByRole('listitem', { name: /^Turn \d+$/ })
/** The case's header (the list's rows have phase badges too). */
const caseHeader = async () => {
  const heading = await screen.findByRole('heading', { level: 1 })
  const header = heading.closest('header')
  if (!header) throw new Error('no header')
  return within(header)
}

test('the header shows the case, what it used, and where it is', async () => {
  const served = openCase(0, {
    turns: 9,
    usage: {
      llm_calls: 11,
      prompt_tokens: 27_000,
      completion_tokens: 3000,
      total_tokens: 30_000,
      cost: 0.0189,
    },
  })
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  expect(
    await screen.findByRole('heading', {
      level: 1,
      name: 'Merma del 4 % en el envasado de la línea 2',
    }),
  ).toBeInTheDocument()
  expect(screen.getByTestId('case-facts')).toHaveTextContent(
    'cliente-acme · 9 turns · $0.02 · 30k tokens',
  )
  // The tab title stays the page's: a case title is conversation content.
  expect(document.title).toBe('Test chat · AYO Admin')
})

test('cost and tokens are left out when nothing reported them', async () => {
  const served = openCase(0, {
    usage: {
      llm_calls: 2,
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
      cost: null,
    },
  })
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  expect(await screen.findByTestId('case-facts')).toHaveTextContent(/^cliente-acme · 9 turns$/)
})

test('an untitled case says so', async () => {
  const served = openCase(4)
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  expect(
    await screen.findByRole('heading', { level: 1, name: 'Untitled case' }),
  ).toBeInTheDocument()
})

test.each([
  ['understand', 'Understand', [], ['Challenge', 'Analyse', 'Action', 'Follow-up']],
  ['analyse', 'Analyse', ['Understand', 'Challenge'], ['Action', 'Follow-up']],
  ['followup', 'Follow-up', ['Understand', 'Challenge', 'Analyse', 'Action'], []],
] as const)('the stepper at %s', async (phase, current, done, ahead) => {
  const served = openCase(0, { phase })
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const steps = within(await screen.findByRole('list', { name: 'Phases' })).getAllByRole('listitem')
  expect(steps).toHaveLength(5)
  const currentStep = steps.find((step) => step.getAttribute('aria-current') === 'step')
  expect(currentStep).toHaveTextContent(`${current} (current)`)
  for (const label of done) {
    expect(steps.find((s) => s.textContent.includes(label))).toHaveTextContent('(completed)')
  }
  for (const label of ahead) {
    expect(steps.find((s) => s.textContent.includes(label))).toHaveTextContent('(not started)')
  }
  expect((await caseHeader()).queryByText('Closed')).toBeNull()
})

test('a closed case has every phase done and a Closed badge', async () => {
  const served = openCase(2)
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const steps = within(await screen.findByRole('list', { name: 'Phases' })).getAllByRole('listitem')
  for (const step of steps) expect(step).toHaveTextContent('(completed)')
  expect(steps.some((step) => step.hasAttribute('aria-current'))).toBe(false)
  expect((await caseHeader()).getByText('Closed')).toHaveAttribute('data-slot', 'badge')
})

test('turns come oldest first: the user text as typed, the reply rendered', async () => {
  const turns = [
    makeTurn(1, { reply: 'Necesito **tres datos**:\n\n- dónde\n- desde cuándo' }),
    {
      ...makeTurn(2),
      user_message: { ...makeTurn(2).user_message, content: 'Uso **negrita**\ny dos líneas' },
    },
  ]
  const served = openCase(0, { turns: 2 }, turns)
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const [first, second] = await turnItems()
  expect(first).toHaveAccessibleName('Turn 1')
  expect(second).toHaveAccessibleName('Turn 2')
  expect(await within(first ?? document.body).findByText('tres datos')).toHaveProperty(
    'tagName',
    'STRONG',
  )
  expect(within(first ?? document.body).getAllByRole('listitem', { name: '' })).toHaveLength(2)
  // The user's text is never Markdown: the asterisks stay.
  expect(within(second ?? document.body).getByText(/Uso \*\*negrita\*\*/)).toBeInTheDocument()
  expect(screen.getByText('Start of the conversation')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Load earlier turns' })).not.toBeInTheDocument()
})

test('a reply renders inert: no script, no image, no javascript: link', async () => {
  const reply = [
    'Hola <script>window.hacked = true</script>',
    '',
    '<img src="x" onerror="window.hacked = true">',
    '',
    '![plano](https://example.com/plano.png)',
    '',
    '[pulsa](javascript:window.hacked=true) y [manual](https://example.com/manual)',
  ].join('\n')
  const served = openCase(0, { turns: 1 }, [makeTurn(1, { reply })])
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const [turn] = await turnItems()
  const scope = within(turn ?? document.body)
  const manual = await scope.findByRole('link', { name: 'manual' })
  expect(manual).toHaveAttribute('rel', 'noopener noreferrer')
  expect(scope.queryByRole('link', { name: 'pulsa' })).toBeNull()
  expect(turn?.querySelector('script, img, [onerror]')).toBeNull()
  expect(scope.getByText(/Image not shown: plano/)).toBeInTheDocument()
  expect((window as { hacked?: boolean }).hacked).toBeUndefined()
})

test('Copy copies the reply as written', async () => {
  const served = openCase(0, { turns: 1 }, [makeTurn(1, { reply: 'Revisa **la junta**.' })])
  serve([served])
  const { user } = renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const [turn] = await turnItems()
  await user.click(within(turn ?? document.body).getByRole('button', { name: 'Copy reply' }))

  expect(await navigator.clipboard.readText()).toBe('Revisa **la junta**.')
})

test('a marker shows only where a turn changed phase', async () => {
  const turns = [
    makeTurn(1, { phase: 'understand' }),
    makeTurn(2, { phase: 'understand', phaseAfter: 'challenge' }),
    makeTurn(3, { phase: 'challenge' }),
  ]
  const served = openCase(0, { turns: 3, phase: 'challenge' }, turns)
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const [first, second, third] = await turnItems()
  expect(second).toHaveTextContent('Moved to Challenge (from Understand)')
  expect(first).not.toHaveTextContent('Moved to')
  expect(third).not.toHaveTextContent('Moved to')
})

test('the latest turns load first, then earlier ones without overlap', async () => {
  const served = openCase(0, { turns: 45 })
  const { turnQueries } = serve([served])
  const { user } = renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  expect(await turnItems()).toHaveLength(20)
  expect(turnQueries).toEqual([{ offset: '25', limit: '20' }])
  expect(screen.queryByText('Start of the conversation')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Load earlier turns' }))
  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(40)
  })
  await user.click(screen.getByRole('button', { name: 'Load earlier turns' }))
  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(45)
  })

  expect(turnQueries).toEqual([
    { offset: '25', limit: '20' },
    { offset: '5', limit: '20' },
    { offset: '0', limit: '5' },
  ])
  const names = (await turnItems()).map((item) => item.getAttribute('aria-label'))
  expect(names).toEqual(Array.from({ length: 45 }, (_, i) => `Turn ${String(i + 1)}`))
  expect(screen.getByText('Start of the conversation')).toBeInTheDocument()
})

test('earlier turns that fail to load keep what is shown, and Retry asks again', async () => {
  const served = openCase(0, { turns: 25 })
  serve([served])
  let fail = true
  server.use(
    http.get(`${API}/admin/cases/:caseId/turns`, ({ request }) => {
      const query = new URL(request.url).searchParams
      const offset = Number(query.get('offset'))
      const limit = Number(query.get('limit'))
      if (offset === 0 && fail) {
        return HttpResponse.json(
          { detail: [{ type: 'internal_error', loc: [], msg: 'Internal error.' }] },
          { status: 500 },
        )
      }
      return HttpResponse.json({
        items: served.turns.slice(offset, offset + limit),
        total: served.turns.length,
        limit,
        offset,
      })
    }),
  )
  const { user } = renderApp(`/chat/${served.detail.case_id}`, { connected: true })
  expect(await turnItems()).toHaveLength(20)

  await user.click(screen.getByRole('button', { name: 'Load earlier turns' }))

  expect(await screen.findByText('Earlier turns could not be loaded.')).toBeInTheDocument()
  expect(await turnItems()).toHaveLength(20)
  fail = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(25)
  })
})

test('Refresh reads the case again and starts from the new latest page', async () => {
  const served = openCase(0, { turns: 25 })
  const tracker = serve([served])
  const { user } = renderApp(`/chat/${served.detail.case_id}`, { connected: true })
  expect(await turnItems()).toHaveLength(20)
  await user.click(screen.getByRole('button', { name: 'Load earlier turns' }))
  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(25)
  })

  // Two turns committed elsewhere meanwhile.
  served.turns.push(makeTurn(26), makeTurn(27))
  served.detail = { ...served.detail, turns: 27 }
  const before = tracker.detailCalls()
  await user.click(screen.getByRole('button', { name: 'Refresh' }))

  await waitFor(async () => {
    const names = (await turnItems()).map((item) => item.getAttribute('aria-label'))
    expect(names).toEqual(Array.from({ length: 20 }, (_, i) => `Turn ${String(i + 8)}`))
  })
  expect(tracker.detailCalls()).toBe(before + 1)
  expect(tracker.turnQueries.at(-1)).toEqual({ offset: '7', limit: '20' })
  expect(screen.getByTestId('case-facts')).toHaveTextContent('27 turns')
})

test('a case with no turns says so', async () => {
  const served = openCase(0, { turns: 0 }, [])
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  expect(await within(await log()).findByText('No messages yet.')).toBeInTheDocument()
})

test.each([
  ['another channel', 3, 'This case came from another channel'],
  ['a closed case', 2, 'This case is closed'],
])('%s opens read-only, saying why', async (_, index, text) => {
  const served = openCase(index)
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  // The shell's "internal use" banner is a note too: find this one by its text.
  const notice = await screen.findByText(new RegExp(text))
  expect(notice.closest('[role="note"]')).not.toBeNull()
})

test('an open web case has no read-only notice', async () => {
  const served = openCase(0)
  serve([served])
  renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  await turnItems()
  expect(screen.queryByText(/can be read here but not continued/)).not.toBeInTheDocument()
})

test('an unknown case says it no longer exists, with a way back', async () => {
  serve([])
  const { user } = renderApp('/chat/0b0e0c0a-0000-4000-8000-000000000000', { connected: true })

  expect(
    await screen.findByRole('heading', { name: 'This case no longer exists' }),
  ).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Back to the cases' }))
  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/chat$/)
  })
  expect(await screen.findByRole('heading', { name: 'Pick a case' })).toBeInTheDocument()
})

test('a malformed id is treated as a missing case', async () => {
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/cases`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
    ),
    http.get(`${API}/admin/cases/:caseId`, () =>
      HttpResponse.json(
        { detail: [{ type: 'uuid_parsing', loc: ['path', 'case_id'], msg: 'Not a UUID.' }] },
        { status: 422 },
      ),
    ),
  )
  renderApp('/chat/not-a-case', { connected: true })

  expect(
    await screen.findByRole('heading', { name: 'This case no longer exists' }),
  ).toBeInTheDocument()
})

test('another failure shows the error, and Retry asks again', async () => {
  const served = openCase(0)
  serve([served])
  let fail = true
  server.use(
    http.get(`${API}/admin/cases/:caseId`, () =>
      fail
        ? HttpResponse.json(
            { detail: [{ type: 'internal_error', loc: [], msg: 'Internal error.' }] },
            { status: 500 },
          )
        : HttpResponse.json(served.detail),
    ),
  )
  const { user } = renderApp(`/chat/${served.detail.case_id}`, { connected: true })

  const alert = await screen.findByRole('alert')
  fail = false
  await user.click(within(alert).getByRole('button', { name: 'Retry' }))

  expect(await turnItems()).toHaveLength(9)
})

test('switching cases shows the other case and keeps the list', async () => {
  const first = openCase(0)
  const second = openCase(1)
  serve([first, second])
  const { user } = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  await turnItems()
  const list = await screen.findByRole('list', { name: 'Cases' })

  await user.click(within(list).getAllByRole('link')[1] ?? document.body)

  expect(
    await screen.findByRole('heading', {
      level: 1,
      name: 'Paradas repetidas de la llenadora L3 en el turno de noche',
    }),
  ).toBeInTheDocument()
  expect(await turnItems()).toHaveLength(14)
  expect(screen.getByRole('list', { name: 'Cases' })).toBe(list)
})

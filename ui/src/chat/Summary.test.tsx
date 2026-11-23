import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { a11yViolations } from '@/test/axe'
import { deferred, serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { CASES } from '@/test/fixtures/cases'
import { makeSettings } from '@/test/fixtures/services'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { WIDE_QUERY } from './inspectorState'

type CaseDetail = components['schemas']['CaseDetail']
type CaseSummary = components['schemas']['CaseSummary']
type Copilot = components['schemas']['CopilotSettings']

function screenWidth(wide: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: wide && query === WIDE_QUERY,
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  )
}

beforeEach(() => {
  screenWidth(true)
})
afterEach(() => {
  vi.restoreAllMocks()
})

const SUMMARY_MODEL = 'openai/gpt-5-mini'

function summary(overrides: Partial<CaseSummary> = {}): CaseSummary {
  return {
    content: '**Problema:** merma en la línea 2.',
    model: SUMMARY_MODEL,
    generated_at: '2026-11-12T10:00:00Z',
    source_version: 10,
    stale: false,
    usage: {
      llm_calls: 1,
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: 1900,
      cost: 0.0011,
    },
    ...overrides,
  }
}

/** The first fixture with `detail` changes, the settings, and a summary endpoint. */
function serve(
  detail: Partial<CaseDetail> = {},
  {
    copilot,
    answer,
  }: {
    copilot?: Partial<Copilot>
    answer?: () => Promise<Response> | Response
  } = {},
) {
  const served: ServedCase[] = CASES.map((item) => servedCase(item))
  const first = served[0]
  if (!first) throw new Error('no case')
  first.detail = { ...first.detail, ...detail }
  const api = serveChat(served)
  const calls = { settings: 0, summary: 0 }
  const base = makeSettings()
  server.use(
    http.get(`${API}/admin/settings`, () => {
      calls.settings += 1
      return HttpResponse.json({
        ...base,
        copilot: { ...base.copilot, summary_model: SUMMARY_MODEL, ...copilot },
      })
    }),
    http.post(`${API}/admin/cases/:caseId/summary`, async () => {
      calls.summary += 1
      if (answer) return answer()
      const made = summary({
        source_version: first.detail.version,
        generated_at: new Date().toISOString(),
      })
      first.detail = {
        ...first.detail,
        summary: made,
        usage: { ...first.detail.usage, llm_calls: first.detail.usage.llm_calls + 1 },
      }
      await delay(1)
      return HttpResponse.json(made)
    }),
  )
  return { first, api, calls }
}

async function openSummary(first: ServedCase) {
  const rendered = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  const inspector = await screen.findByRole('complementary', { name: 'Inspector' })
  await rendered.user.click(within(inspector).getByRole('tab', { name: 'Summary' }))
  await within(inspector).findByRole('heading', { name: 'AI summary' })
  return { ...rendered, inspector }
}

const group = (root: HTMLElement, name: string) => within(root).getByRole('group', { name })
const items = (root: HTMLElement, name: string) =>
  within(group(root, name))
    .queryAllByRole('listitem')
    .map((li) => li.textContent)

function errorBody(status: number, type: string) {
  return HttpResponse.json({ detail: [{ type, loc: [], msg: 'No.' }] }, { status })
}

test('the structured summary is built from the case record, empty sections said', async () => {
  const { first } = serve({
    fields: { what: 'Merma del 4 %', where: 'Línea 2', since: null, standard: 'Máximo 1 %' },
    events: [
      {
        id: 1,
        event_type: 'evidence',
        content: 'Sube de noche',
        state_at_time: 'challenge',
        created_at: '2026-11-12T09:00:00Z',
      },
      {
        id: 2,
        event_type: 'hypothesis',
        content: 'Film más grueso',
        state_at_time: 'analyse',
        created_at: '2026-11-12T09:05:00Z',
      },
      {
        id: 3,
        event_type: 'hypothesis_discarded',
        content: 'No es la temperatura',
        state_at_time: 'analyse',
        created_at: '2026-11-12T09:06:00Z',
      },
    ],
    actions: [
      {
        id: 1,
        description: 'Probar el film de 50 µm',
        owner: 'Marta',
        due_date: '2026-11-20',
        status: 'pending',
        overdue: true,
      },
      {
        id: 2,
        description: 'Formar al turno',
        owner: 'Luis',
        due_date: '2026-11-25',
        status: 'done',
        overdue: false,
      },
    ],
  })
  const { inspector } = await openSummary(first)

  expect(
    within(inspector).getByText(/From the case record, no model call\. Analyse, open\./),
  ).toBeVisible()
  expect(items(inspector, 'Problem')).toEqual([
    'What: Merma del 4 %',
    'Where: Línea 2',
    'Standard: Máximo 1 %',
  ])
  expect(within(group(inspector, 'Validated cause')).getByText('Not validated yet')).toBeVisible()
  expect(items(inspector, 'Hypotheses')).toEqual(['Film más grueso'])
  expect(items(inspector, 'Discarded hypotheses')).toEqual(['No es la temperatura'])
  expect(items(inspector, 'Evidence')).toEqual(['Sube de noche'])
  expect(items(inspector, 'Actions')).toEqual([
    'Probar el film de 50 µm (Marta, due 2026-11-20, pending, overdue)',
    'Formar al turno (Luis, due 2026-11-25, done)',
  ])
  expect(await a11yViolations(inspector)).toEqual([])
})

test('no AI summary yet; the dialog names the cached model; Cancel calls nothing', async () => {
  const { first, calls } = serve()
  const { user, inspector } = await openSummary(first)
  expect(within(inspector).getByText('No AI summary yet.')).toBeVisible()

  await user.click(within(inspector).getByRole('button', { name: 'Generate AI summary' }))
  const dialog = await screen.findByRole('alertdialog', { name: 'Generate an AI summary?' })
  expect(dialog).toHaveTextContent(`one billed call to ${SUMMARY_MODEL} through OpenRouter`)
  expect(dialog).not.toHaveTextContent('replaces')
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => {
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })
  expect(calls.summary).toBe(0)

  // Read once when the tab opened, then from the cache: switching tabs reads nothing.
  await user.click(within(inspector).getByRole('tab', { name: 'State' }))
  await user.click(within(inspector).getByRole('tab', { name: 'Summary' }))
  await user.click(await within(inspector).findByRole('button', { name: 'Generate AI summary' }))
  expect(await screen.findByRole('alertdialog')).toHaveTextContent(SUMMARY_MODEL)
  expect(calls.settings).toBe(1)
})

test('without a provider key the dialog says the call will be refused', async () => {
  const { first } = serve({}, { copilot: { configured: false } })
  const { user, inspector } = await openSummary(first)
  await user.click(within(inspector).getByRole('button', { name: 'Generate AI summary' }))
  expect(await screen.findByRole('alertdialog')).toHaveTextContent('No model provider key')
})

test('generating shows a skeleton, then the summary, and the case is read again', async () => {
  const gate = deferred()
  const { first, calls, api } = serve()
  const { user, inspector } = await openSummary(first)
  const before = api.caseCalls()
  server.use(
    http.post(`${API}/admin/cases/:caseId/summary`, async () => {
      calls.summary += 1
      await gate.promise
      const made = summary({ source_version: first.detail.version })
      first.detail = { ...first.detail, summary: made }
      return HttpResponse.json(made)
    }),
  )

  await user.click(within(inspector).getByRole('button', { name: 'Generate AI summary' }))
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Generate' }),
  )
  expect(await within(inspector).findByLabelText('Generating the summary')).toBeVisible()
  expect(within(inspector).getByRole('button', { name: 'Generating…' })).toBeDisabled()

  gate.resolve()
  expect(await within(inspector).findByText('Problema:')).toBeVisible()
  expect(within(inspector).getByTestId('summary-meta')).toHaveTextContent(`${SUMMARY_MODEL} · `)
  expect(within(inspector).getByTestId('summary-meta')).toHaveTextContent(
    '1 call · 1.9k tokens · $0.0011',
  )
  expect(within(inspector).getByRole('button', { name: 'Regenerate' })).toBeEnabled()
  expect(calls.summary).toBe(1)
  await waitFor(() => {
    expect(api.caseCalls()).toBeGreaterThan(before)
  })
})

test('a stale summary says so, and regenerating asks to replace it', async () => {
  const { first } = serve({ version: 14, summary: summary({ source_version: 12, stale: true }) })
  const { user, inspector } = await openSummary(first)
  const note = within(inspector).getByRole('note')
  expect(note).toHaveTextContent('Stale')
  expect(note).toHaveTextContent('Made from version 12; the case is at version 14 now.')

  await user.click(within(inspector).getByRole('button', { name: 'Regenerate' }))
  const dialog = await screen.findByRole('alertdialog', { name: 'Regenerate the AI summary?' })
  expect(dialog).toHaveTextContent('It replaces the current summary.')
  expect(within(dialog).getByRole('button', { name: 'Regenerate' })).toBeVisible()
})

test('a current summary shows no stale note, and renders its Markdown inert', async () => {
  const { first } = serve({
    summary: summary({
      content:
        'Hola <script>alert(1)</script> <img src=x onerror="alert(1)"> [x](javascript:alert(1))',
    }),
  })
  const { inspector } = await openSummary(first)
  expect(within(inspector).queryByRole('note')).toBeNull()
  await within(inspector).findByText(/Hola/)
  expect(inspector.querySelector('script')).toBeNull()
  expect(inspector.querySelector('img')).toBeNull()
  expect(inspector.querySelector('a[href^="javascript"]')).toBeNull()
})

test.each([
  [409, 'case_empty', 'nothing to summarise'],
  [404, 'case_not_found', 'This case no longer exists.'],
  [502, 'llm_credits', 'The language model failed (llm_credits)'],
  [503, 'llm_not_configured', 'no language model configured'],
])('a %i %s keeps the old summary and says why', async (status, type, message) => {
  const { first } = serve(
    { summary: summary({ content: 'Resumen anterior' }) },
    { answer: () => errorBody(status, type) },
  )
  const { user, inspector } = await openSummary(first)
  await user.click(within(inspector).getByRole('button', { name: 'Regenerate' }))
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Regenerate' }),
  )

  expect(await within(inspector).findByRole('alert')).toHaveTextContent(message)
  expect(within(inspector).getByText('Resumen anterior')).toBeVisible()
})

test('a network failure says the summary may still have been made', async () => {
  const { first } = serve({}, { answer: () => HttpResponse.error() })
  const { user, inspector } = await openSummary(first)
  await user.click(within(inspector).getByRole('button', { name: 'Generate AI summary' }))
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Generate' }),
  )
  expect(await within(inspector).findByRole('alert')).toHaveTextContent('may still have been made')
})

test('a case with no turns cannot be summarised', async () => {
  const { first, calls } = serve({ turns: 0 })
  first.turns = []
  const { inspector } = await openSummary(first)
  expect(within(inspector).getByRole('button', { name: 'Generate AI summary' })).toBeDisabled()
  expect(within(inspector).getByText('Nothing to summarise until the first turn.')).toBeVisible()
  expect(calls.summary).toBe(0)
})

test('leaving the tab while it runs keeps it running, and the result shows on return', async () => {
  const gate = deferred()
  const { first } = serve()
  const { user, inspector } = await openSummary(first)
  server.use(
    http.post(`${API}/admin/cases/:caseId/summary`, async () => {
      await gate.promise
      const made = summary({ source_version: first.detail.version })
      first.detail = { ...first.detail, summary: made }
      return HttpResponse.json(made)
    }),
  )
  await user.click(within(inspector).getByRole('button', { name: 'Generate AI summary' }))
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Generate' }),
  )
  await within(inspector).findByLabelText('Generating the summary')

  await user.click(within(inspector).getByRole('tab', { name: 'State' }))
  await user.click(within(inspector).getByRole('tab', { name: 'Summary' }))
  // Still generating: no second call can start.
  expect(await within(inspector).findByRole('button', { name: 'Generating…' })).toBeDisabled()
  gate.resolve()
  expect(await within(inspector).findByText('Problema:')).toBeVisible()
})

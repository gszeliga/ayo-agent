import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'
import { a11yViolations } from '@/test/axe'
import { serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { CASES, makeTurn } from '@/test/fixtures/cases'
import { makeDocument } from '@/test/fixtures/documents'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { WIDE_QUERY } from './inspectorState'

type CaseTurn = components['schemas']['CaseTurn']
type CaseTrace = components['schemas']['CaseTrace']

const DOC = 'upload-3f9a1c2b7d4e'
const location = () => screen.getByTestId('location').textContent

/** The window as wide as `wide` says: the setup's stub matches nothing (narrow). */
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

afterEach(() => {
  vi.restoreAllMocks()
})

function withTrace(turn: CaseTurn, trace: Partial<CaseTrace>): CaseTurn {
  return { ...turn, trace: { ...turn.trace, ...trace } }
}

/** The first fixture (open, web, 9 turns), its turns as given, and the other cases. */
function cases(turns?: CaseTurn[], detail: Partial<ServedCase['detail']> = {}): ServedCase[] {
  const served = CASES.map((item) => servedCase(item))
  const first = served[0]
  if (first) {
    if (turns) first.turns = turns
    first.detail = { ...first.detail, turns: first.turns.length, ...detail }
  }
  return served
}

async function openTrace(served: ServedCase[]) {
  const first = served[0]
  if (!first) throw new Error('no case')
  serveChat(served)
  const rendered = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  const inspector = await screen.findByRole('complementary', { name: 'Inspector' })
  await rendered.user.click(within(inspector).getByRole('tab', { name: 'Trace' }))
  await within(inspector).findByRole('list', { name: 'Traces' })
  return { ...rendered, inspector, caseId: first.detail.case_id }
}

const entry = (root: HTMLElement, turn: number) =>
  within(root).getByRole('listitem', { name: `Trace of turn ${String(turn)}` })
const toggleOf = (item: HTMLElement) => within(item).getAllByRole('button')[0] as HTMLElement

const RICH_TURN = withTrace(makeTurn(3, { phase: 'challenge', phaseAfter: 'analyse' }), {
  capped: true,
  retrieval_error: 'embedding_failed',
  duration_ms: 4500,
  tool_calls: [
    { name: 'log_event', ok: true, error_code: null, target: null, missing: [] },
    {
      name: 'propose_transition',
      ok: false,
      error_code: 'criteria_not_met',
      target: 'action',
      missing: ['validated_cause', 'evidence_count'],
    },
    { name: 'propose_transition', ok: true, error_code: null, target: 'analyse', missing: [] },
  ],
  usage: {
    llm_calls: 4,
    prompt_tokens: 9000,
    completion_tokens: 700,
    total_tokens: 9700,
    cost: 0.0084,
  },
})

test('each entry sums up its turn, newest first, the newest open', async () => {
  screenWidth(true)
  const { inspector } = await openTrace(cases([makeTurn(1), makeTurn(2), RICH_TURN]))

  const items = within(within(inspector).getByRole('list', { name: 'Traces' })).getAllByRole(
    'listitem',
    { name: /^Trace of turn/ },
  )
  expect(items.map((li) => li.getAttribute('aria-label'))).toEqual([
    'Trace of turn 3',
    'Trace of turn 2',
    'Trace of turn 1',
  ])
  const rich = entry(inspector, 3)
  expect(toggleOf(rich)).toHaveAttribute('aria-expanded', 'true')
  expect(toggleOf(entry(inspector, 2))).toHaveAttribute('aria-expanded', 'false')
  expect(toggleOf(rich)).toHaveTextContent('Turn 3Challenge → Analyse')
  expect(toggleOf(rich)).toHaveTextContent('4 calls · $0.0084 · 4.5 s')
  for (const badge of ['Capped', 'Retrieval failed', '1 refused']) {
    expect(within(toggleOf(rich)).getByText(badge)).toBeVisible()
  }
  expect(within(toggleOf(entry(inspector, 2))).queryByText('Capped')).toBeNull()

  const calls = within(within(rich).getByRole('group', { name: 'Tool calls' })).getAllByRole(
    'listitem',
  )
  expect(calls.map((li) => li.textContent)).toEqual([
    'log_event accepted',
    'propose_transition → Action refused (criteria_not_met) · missing: validated_cause, evidence_count',
    'propose_transition → Analyse accepted',
  ])
  expect(within(rich).getByText(/The knowledge search failed/)).toHaveTextContent(
    'embedding_failed',
  )
  const details = within(rich).getByText('Model').closest('dl') as HTMLElement
  expect(details).toHaveTextContent('openai/gpt-5-mini')
  expect(details).toHaveTextContent('draft-3')
  expect(details).toHaveTextContent('9.7k tokens (9000 in, 700 out)')
  expect(details).toHaveTextContent('$0.0084')
  expect(within(inspector).getByText(/Never shown: chunk text, tool arguments/)).toBeVisible()
})

test('entries open and close, and stay so when switching tabs', async () => {
  screenWidth(true)
  const { user, inspector } = await openTrace(cases([makeTurn(1), makeTurn(2)]))
  await user.click(toggleOf(entry(inspector, 1)))
  await user.click(toggleOf(entry(inspector, 2)))
  expect(toggleOf(entry(inspector, 1))).toHaveAttribute('aria-expanded', 'true')
  expect(toggleOf(entry(inspector, 2))).toHaveAttribute('aria-expanded', 'false')

  await user.click(within(inspector).getByRole('tab', { name: 'State' }))
  await user.click(within(inspector).getByRole('tab', { name: 'Trace' }))
  expect(toggleOf(entry(inspector, 1))).toHaveAttribute('aria-expanded', 'true')
  expect(toggleOf(entry(inspector, 2))).toHaveAttribute('aria-expanded', 'false')
})

test('retrieved chunks: a link to the chunk, changed since, deleted and untitled', async () => {
  screenWidth(true)
  const turn = withTrace(makeTurn(1), {
    retrieved: [
      {
        chunk_id: 'c1',
        chunk_index: 27,
        doc_id: DOC,
        document_deleted: false,
        document_title: 'PRO-014 Control del sellado',
        similarity: 0.8234,
      },
      {
        chunk_id: 'c2',
        chunk_index: null,
        doc_id: 'upload-aaaaaaaaaaaa',
        document_deleted: false,
        document_title: 'Método de los cinco porqués',
        similarity: 0.61,
      },
      {
        chunk_id: 'c3',
        chunk_index: null,
        doc_id: 'upload-bbbbbbbbbbbb',
        document_deleted: true,
        document_title: null,
        similarity: 0.58,
      },
      {
        chunk_id: 'c4',
        chunk_index: 0,
        doc_id: 'upload-cccccccccccc',
        document_deleted: false,
        document_title: null,
        similarity: 0.5,
      },
    ],
  })
  const { inspector } = await openTrace(cases([turn]))
  const rows = within(within(inspector).getByRole('group', { name: 'Retrieved' })).getAllByRole(
    'listitem',
  )
  const [kept, changed, deleted, untitled] = rows as [
    HTMLElement,
    HTMLElement,
    HTMLElement,
    HTMLElement,
  ]

  expect(kept).toHaveTextContent('Similarity 0.82')
  expect(within(kept).getByRole('link', { name: 'PRO-014 Control del sellado' })).toHaveAttribute(
    'href',
    `/documents/${DOC}?tab=chunks&cpage=2`,
  )
  expect(kept).toHaveTextContent('chunk #27')
  expect(
    within(changed).getByRole('link', { name: 'Método de los cinco porqués' }),
  ).toHaveAttribute('href', '/documents/upload-aaaaaaaaaaaa')
  expect(within(changed).getByText('Changed since')).toBeVisible()
  expect(deleted).toHaveTextContent('Deleted document')
  expect(within(deleted).queryByRole('link')).toBeNull()
  expect(within(untitled).getByRole('link', { name: 'Untitled document' })).toBeVisible()
  expect(await a11yViolations(inspector)).toEqual([])
})

test('a chunk opens outlined "From the chat", and the back link returns to the case', async () => {
  screenWidth(true)
  const turn = withTrace(makeTurn(1), {
    retrieved: [
      {
        chunk_id: 'c1',
        chunk_index: 1,
        doc_id: DOC,
        document_deleted: false,
        document_title: 'PRO-014 Control del sellado',
        similarity: 0.8,
      },
    ],
  })
  const doc = makeDocument({ doc_id: DOC, chunk_count: 3 })
  server.use(
    http.get(`${API}/admin/documents/${DOC}`, () => HttpResponse.json(doc)),
    http.get(`${API}/admin/documents/${DOC}/chunks`, () =>
      HttpResponse.json({
        items: [0, 1, 2].map((i) => ({
          chunk_index: i,
          heading: 'PRO-014 > Pasos',
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
  const { user, inspector, caseId } = await openTrace(cases([turn]))
  await user.click(within(inspector).getByRole('link', { name: 'PRO-014 Control del sellado' }))

  const chunk = await screen.findByRole('article', { name: 'Chunk 1' })
  expect(chunk).toHaveAttribute('data-highlighted', 'true')
  expect(within(chunk).getByText('From the chat')).toBeVisible()
  expect(location()).toBe(`/documents/${DOC}?tab=chunks`)

  await user.click(within(screen.getByRole('main')).getByRole('link', { name: 'Chat' }))
  expect(location()).toBe(`/chat/${caseId}`)
  expect(await screen.findByRole('heading', { level: 1 })).toBeVisible()
})

test('case totals: the case, its turns and its AI summary', async () => {
  screenWidth(true)
  const served = cases([makeTurn(1)], {
    usage: {
      llm_calls: 12,
      prompt_tokens: 30_000,
      completion_tokens: 3000,
      total_tokens: 33_000,
      cost: 0.03,
    },
    summary: {
      content: 'Resumen',
      model: 'openai/gpt-5-mini',
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
    },
  })
  const { inspector } = await openTrace(served)
  expect(within(inspector).getByTestId('case-total')).toHaveTextContent(
    '12 calls · 33k tokens · $0.03',
  )
  expect(within(inspector).getByTestId('turns-usage')).toHaveTextContent(
    '11 calls · 31.1k tokens · $0.03',
  )
  expect(within(inspector).getByTestId('summary-usage')).toHaveTextContent(
    '1 call · 1.9k tokens · $0.0011',
  )
})

test('case totals without a summary or reported figures', async () => {
  screenWidth(true)
  const served = cases([makeTurn(1)], {
    usage: {
      llm_calls: 2,
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
      cost: null,
    },
  })
  const { inspector } = await openTrace(served)
  expect(within(inspector).getByTestId('case-total')).toHaveTextContent(/^2 calls$/)
  expect(within(inspector).getByTestId('turns-usage')).toHaveTextContent(/^2 calls$/)
  expect(within(inspector).queryByTestId('summary-usage')).toBeNull()
})

test('the Trace tab loads earlier turns, the same pages as the chat', async () => {
  screenWidth(true)
  const { user, inspector } = await openTrace(
    cases(Array.from({ length: 25 }, (_, i) => makeTurn(i + 1))),
  )
  const list = () => within(inspector).getByRole('list', { name: 'Traces' })
  expect(within(list()).getAllByRole('listitem', { name: /^Trace of turn/ })).toHaveLength(20)
  await user.click(within(inspector).getByRole('button', { name: 'Load earlier turns' }))
  await waitFor(() => {
    expect(within(list()).getAllByRole('listitem', { name: /^Trace of turn/ })).toHaveLength(25)
  })
  expect(within(inspector).getByText('Start of the conversation')).toBeVisible()
  // The chat shows them too.
  const log = screen.getByRole('log', { name: 'Conversation' })
  expect(within(log).getAllByRole('listitem', { name: /^Turn \d+$/ })).toHaveLength(25)
})

test('a turn chip opens the hidden inspector on that trace, open and outlined', async () => {
  screenWidth(true)
  const served = cases([makeTurn(1), makeTurn(2), makeTurn(3)])
  const first = served[0]
  if (!first) throw new Error('no case')
  serveChat(served)
  const { user } = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  await user.click(await screen.findByRole('button', { name: 'Inspector' }))
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()

  await user.click(await screen.findByRole('button', { name: 'Turn 1 · trace' }))
  const inspector = await screen.findByRole('complementary', { name: 'Inspector' })
  expect(within(inspector).getByRole('tab', { name: 'Trace', selected: true })).toBeVisible()
  const one = entry(inspector, 1)
  expect(one).toHaveAttribute('data-focused', 'true')
  expect(toggleOf(one)).toHaveAttribute('aria-expanded', 'true')
  // The newest stays open as it was by default; another chip moves the outline.
  expect(toggleOf(entry(inspector, 3))).toHaveAttribute('aria-expanded', 'true')
  await user.click(screen.getByRole('button', { name: 'Turn 2 · trace' }))
  expect(entry(inspector, 2)).toHaveAttribute('data-focused', 'true')
  expect(entry(inspector, 1)).not.toHaveAttribute('data-focused')
})

test('on a narrow screen a turn chip opens the drawer on that trace', async () => {
  screenWidth(false)
  const served = cases([makeTurn(1), makeTurn(2)])
  const first = served[0]
  if (!first) throw new Error('no case')
  serveChat(served)
  const { user } = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  await user.click(await screen.findByRole('button', { name: 'Turn 1 · trace' }))
  const drawer = await screen.findByRole('dialog', { name: 'Inspector' })
  const one = await within(drawer).findByRole('listitem', { name: 'Trace of turn 1' })
  expect(one).toHaveAttribute('data-focused', 'true')
  expect(toggleOf(one)).toHaveAttribute('aria-expanded', 'true')
  expect(await a11yViolations(drawer)).toEqual([])
})

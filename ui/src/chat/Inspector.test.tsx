import { screen, waitFor, within } from '@testing-library/react'

import type { components } from '@/api/schema'
import { a11yViolations } from '@/test/axe'
import { deferred, serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { CASES } from '@/test/fixtures/cases'
import { renderApp } from '@/test/render'

import { WIDE_QUERY } from './inspectorState'

type CaseEvent = components['schemas']['CopilotSessionEvent']
type CaseAction = components['schemas']['CopilotSessionAction']

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

let nextId = 0

function event(event_type: CaseEvent['event_type'], content: string): CaseEvent {
  nextId += 1
  return {
    id: nextId,
    event_type,
    content,
    state_at_time: 'challenge',
    created_at: '2026-11-12T09:3' + String(nextId % 10) + ':00Z',
  }
}

function action(overrides: Partial<CaseAction>): CaseAction {
  nextId += 1
  return {
    id: nextId,
    description: 'Revisar la junta de la llenadora',
    owner: 'Marta (mantenimiento)',
    due_date: '2026-11-20',
    status: 'pending',
    overdue: false,
    ...overrides,
  }
}

/** The fixtures as served cases; the first one (open, web) gets `events` and `actions`. */
function cases(events: CaseEvent[] = [], actions: CaseAction[] = []): ServedCase[] {
  const served = CASES.map((item) => servedCase(item))
  const first = served[0]
  if (first) first.detail = { ...first.detail, events, actions }
  return served
}

async function openFirst(served: ServedCase[]) {
  const first = served[0]
  if (!first) throw new Error('no case')
  const api = serveChat(served)
  const rendered = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  await screen.findByRole('heading', { level: 1 })
  return { ...rendered, api }
}

const panel = () => screen.findByRole('complementary', { name: 'Inspector' })
const toggle = () => screen.findByRole('button', { name: 'Inspector' })
const section = (root: HTMLElement, name: string) =>
  within(within(root).getByRole('region', { name: new RegExp(`^${name}`) }))

test('the State tab shows the facts, then each kind of annotation as text', async () => {
  screenWidth(true)
  const served = cases([
    event('hypothesis', 'Desgaste de la junta'),
    event('evidence', 'La merma sube en el turno de noche'),
    event('hypothesis', 'Ajuste de la dosificadora <img src=x onerror="alert(1)">'),
    event('hypothesis_discarded', 'No es la temperatura'),
  ])
  const first = served[0]
  if (first) first.detail.fields = { ...first.detail.fields, since: null }
  await openFirst(served)

  const inspector = await panel()
  expect(within(inspector).getByRole('tab', { name: 'State', selected: true })).toBeVisible()
  const facts = section(inspector, 'Facts')
  expect(facts.getByText('Where').nextSibling).toHaveTextContent('Línea 2, envasadora')
  expect(facts.getByText('Standard').nextSibling).toHaveTextContent('Merma máxima del 1 %')
  expect(facts.getByText('Since').nextSibling).toHaveTextContent('Not recorded yet')

  const headings = within(inspector)
    .getAllByRole('heading', { level: 2 })
    .map((h) => h.textContent)
  expect(headings).toEqual([
    'Facts',
    'Hypotheses (2)',
    'Discarded hypotheses (1)',
    'Validated cause (0)',
    'Evidence (1)',
  ])
  const hypotheses = section(inspector, 'Hypotheses')
    .getAllByRole('listitem')
    .map((li) => li.firstChild?.textContent)
  expect(hypotheses).toEqual([
    'Desgaste de la junta',
    'Ajuste de la dosificadora <img src=x onerror="alert(1)">',
  ])
  expect(inspector.querySelector('img')).toBeNull()
  expect(section(inspector, 'Hypotheses').getAllByRole('listitem')[0]).toHaveTextContent(
    'In Challenge',
  )
  expect(section(inspector, 'Discarded hypotheses').getByText(/not linked/)).toBeVisible()
  expect(section(inspector, 'Validated cause').getByText('None yet')).toBeVisible()
})

test('the Actions tab lists every action and takes overdue from the API', async () => {
  screenWidth(true)
  const served = cases(
    [],
    [
      // Long past, but the API says it is not overdue: no badge.
      action({ description: 'Cambiar la junta', due_date: '2020-01-01', overdue: false }),
      // In the future, but the API says overdue: the badge shows.
      action({ description: 'Medir la presión', due_date: '2099-12-31', overdue: true }),
      action({ description: 'Formar al turno de noche', owner: 'Luis', status: 'done' }),
    ],
  )
  const { user } = await openFirst(served)

  const inspector = await panel()
  await user.click(within(inspector).getByRole('tab', { name: 'Actions' }))
  const table = within(inspector).getByRole('table', { name: 'Actions' })
  expect(
    within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent),
  ).toEqual(['Action', 'Owner', 'Due', 'Status'])
  const rows = within(table).getAllByRole('row').slice(1)
  expect(rows).toHaveLength(3)
  const [past, future, done] = rows as [HTMLElement, HTMLElement, HTMLElement]
  expect(past).toHaveTextContent('Cambiar la junta')
  expect(past).toHaveTextContent('Marta (mantenimiento)')
  expect(past).toHaveTextContent('2020-01-01')
  expect(past).toHaveTextContent('Pending')
  expect(within(past).queryByText('Overdue')).toBeNull()
  expect(within(future).getByText('Overdue')).toBeVisible()
  expect(done).toHaveTextContent('Luis')
  expect(done).toHaveTextContent('Done')
})

test('a case without actions says so', async () => {
  screenWidth(true)
  const { user } = await openFirst(cases())
  const inspector = await panel()
  await user.click(within(inspector).getByRole('tab', { name: 'Actions' }))
  expect(within(inspector).getByText('No actions yet')).toBeVisible()
})

test('the inspector hides and shows, and stays as left when switching cases', async () => {
  screenWidth(true)
  const served = cases()
  const { user } = await openFirst(served)
  await panel()
  expect(await toggle()).toHaveAttribute('aria-pressed', 'true')

  // The tab chosen survives switching cases too.
  await user.click(within(await panel()).getByRole('tab', { name: 'Actions' }))
  await user.click(await toggle())
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
  expect(await toggle()).toHaveAttribute('aria-pressed', 'false')

  await user.click(screen.getByRole('link', { name: /Paradas repetidas/ }))
  await screen.findByRole('heading', { level: 1, name: /Paradas repetidas/ })
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()

  await user.click(await toggle())
  const inspector = await panel()
  expect(within(inspector).getByRole('tab', { name: 'Actions', selected: true })).toBeVisible()
})

test('on a narrow screen the inspector is a drawer: closed, opened, shut with Esc', async () => {
  screenWidth(false)
  const { user } = await openFirst(cases([event('evidence', 'La merma sube de noche')]))
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
  const button = await toggle()
  expect(button).not.toHaveAttribute('aria-pressed')
  expect(button).toHaveAttribute('aria-haspopup', 'dialog')

  await user.click(button)
  const drawer = await screen.findByRole('dialog', { name: 'Inspector' })
  expect(within(drawer).getByText('La merma sube de noche')).toBeVisible()
  expect(await a11yViolations(drawer)).toEqual([])

  await user.keyboard('{Escape}')
  await waitFor(() => {
    expect(screen.queryByRole('dialog', { name: 'Inspector' })).toBeNull()
  })
  expect(button).toHaveFocus()
})

test('after a turn the inspector shows the case as the API now has it', async () => {
  screenWidth(true)
  const served = cases()
  const { user, api } = await openFirst(served)
  const inspector = await panel()
  expect(section(inspector, 'Evidence').getByText('None yet')).toBeVisible()

  const gate = deferred()
  api.control.gate = gate.promise
  await user.type(
    await screen.findByRole('textbox', { name: 'Message' }),
    'La merma sube de noche{Enter}',
  )
  // The turn records evidence while it runs.
  const first = served[0]
  if (first) first.detail = { ...first.detail, events: [event('evidence', 'Sube de noche')] }
  gate.resolve()

  expect(await within(await panel()).findByText('Sube de noche')).toBeVisible()
})

test('the inspector has no accessibility violations', async () => {
  screenWidth(true)
  const { user } = await openFirst(
    cases(
      [event('hypothesis', 'Desgaste de la junta'), event('validated_cause', 'Junta gastada')],
      [action({ overdue: true }), action({ status: 'done' })],
    ),
  )
  const inspector = await panel()
  expect(await a11yViolations(inspector)).toEqual([])
  await user.click(within(inspector).getByRole('tab', { name: 'Actions' }))
  expect(await a11yViolations(inspector)).toEqual([])
})

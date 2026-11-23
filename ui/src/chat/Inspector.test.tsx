import { screen, waitFor, within } from '@testing-library/react'

import type { components } from '@/api/schema'
import { a11yViolations } from '@/test/axe'
import { deferred, serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { CASES } from '@/test/fixtures/cases'
import { renderApp } from '@/test/render'

import { WIDE_QUERY } from './inspectorState'
import { INSPECTOR_LIMITS } from './panelWidth'

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

const WIDTH_KEY = 'ayo.chat.inspector-width'
const resizer = () => screen.findByRole('separator', { name: 'Resize inspector' })
const panel = () => screen.findByRole('complementary', { name: 'Inspector' })
const hideButton = () => screen.findByRole('button', { name: 'Hide inspector' })
const showButton = () => screen.findByRole('button', { name: 'Show inspector' })
const rail = () => screen.findByRole('complementary', { name: 'Inspector (collapsed)' })
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
    'Inspector',
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
  const list = within(inspector).getByRole('list', { name: 'Actions' })
  const items = within(list).getAllByRole('listitem')
  expect(items).toHaveLength(3)
  const [past, future, done] = items as [HTMLElement, HTMLElement, HTMLElement]
  expect(past).toHaveTextContent('Cambiar la junta')
  expect(within(past).getByText('Owner').nextSibling).toHaveTextContent('Marta (mantenimiento)')
  expect(within(past).getByText('Due').nextSibling).toHaveTextContent('2020-01-01')
  expect(within(past).getByText('Pending')).toBeVisible()
  expect(within(past).queryByText('Overdue')).toBeNull()
  expect(within(future).getByText('Overdue')).toBeVisible()
  expect(within(done).getByText('Owner').nextSibling).toHaveTextContent('Luis')
  expect(within(done).getByText('Done')).toBeVisible()
})

test('a case without actions says so', async () => {
  screenWidth(true)
  const { user } = await openFirst(cases())
  const inspector = await panel()
  await user.click(within(inspector).getByRole('tab', { name: 'Actions' }))
  expect(within(inspector).getByText('No actions yet')).toBeVisible()
})

test('the inspector hides to its rail and back, and stays as left when switching cases', async () => {
  screenWidth(true)
  const served = cases()
  const { user } = await openFirst(served)
  await panel()
  expect(screen.queryByRole('complementary', { name: 'Inspector (collapsed)' })).toBeNull()
  expect(await hideButton()).toHaveAttribute('aria-expanded', 'true')

  // The tab chosen survives switching cases too.
  await user.click(within(await panel()).getByRole('tab', { name: 'Actions' }))
  await user.click(await hideButton())
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
  expect(await showButton()).toHaveAttribute('aria-expanded', 'false')
  expect(await showButton()).not.toHaveAttribute('aria-haspopup')
  expect(await a11yViolations(await rail())).toEqual([])

  await user.click(screen.getByRole('link', { name: /Paradas repetidas/ }))
  await screen.findByRole('heading', { level: 1, name: /Paradas repetidas/ })
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()

  await user.click(await showButton())
  const inspector = await panel()
  expect(within(inspector).getByRole('tab', { name: 'Actions', selected: true })).toBeVisible()
  expect(screen.queryByRole('complementary', { name: 'Inspector (collapsed)' })).toBeNull()
})

test('both panels use the same toggle, mirrored', async () => {
  screenWidth(true)
  const { user } = await openFirst(cases())
  const hideCases = screen.getByRole('button', { name: 'Hide cases' })
  expect(hideCases).toHaveAttribute('aria-expanded', 'true')
  expect(await hideButton()).toHaveAttribute('aria-expanded', 'true')
  // The case header has no inspector toggle any more.
  const header = screen.getByRole('heading', { level: 1 }).closest('header') as HTMLElement
  expect(within(header).queryByRole('button', { name: /inspector/i })).toBeNull()

  await user.click(hideCases)
  await user.click(await hideButton())
  expect(screen.getByRole('button', { name: 'Show cases' })).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  expect(await showButton()).toHaveAttribute('aria-expanded', 'false')
})

test("the rail's tab buttons open the inspector on their tab", async () => {
  screenWidth(true)
  const { user } = await openFirst(cases())
  await user.click(await hideButton())
  await user.click(within(await rail()).getByRole('button', { name: 'Show trace' }))
  expect(within(await panel()).getByRole('tab', { name: 'Trace', selected: true })).toBeVisible()
  await user.click(await hideButton())
  await user.click(within(await rail()).getByRole('button', { name: 'Show summary' }))
  expect(within(await panel()).getByRole('tab', { name: 'Summary', selected: true })).toBeVisible()
})

test("the rail's Actions button shows the API's overdue count, not one worked out here", async () => {
  screenWidth(true)
  const served = cases(
    [],
    [
      action({ due_date: '2020-01-01', overdue: false }),
      action({ due_date: '2099-12-31', overdue: true }),
    ],
  )
  const { user } = await openFirst(served)
  await user.click(await hideButton())
  const button = within(await rail()).getByRole('button', { name: 'Show actions (1 overdue)' })
  expect(within(button).getByTestId('overdue-dot')).toBeInTheDocument()
})

test('a case without overdue actions has no dot on the rail', async () => {
  screenWidth(true)
  const { user } = await openFirst(cases([], [action({ overdue: false })]))
  await user.click(await hideButton())
  const button = within(await rail()).getByRole('button', { name: 'Show actions' })
  expect(within(button).queryByTestId('overdue-dot')).toBeNull()
})

test('on a narrow screen the rail opens the drawer on its tab; Esc closes it', async () => {
  screenWidth(false)
  const { user } = await openFirst(cases([event('evidence', 'La merma sube de noche')]))
  expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
  const button = await showButton()
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

  const actions = within(await rail()).getByRole('button', { name: 'Show actions' })
  await user.click(actions)
  const again = await screen.findByRole('dialog', { name: 'Inspector' })
  expect(within(again).getByRole('tab', { name: 'Actions', selected: true })).toBeVisible()
  await user.keyboard('{Escape}')
  await waitFor(() => {
    expect(actions).toHaveFocus()
  })
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

test('the inspector is resized from its edge with the keyboard, within its limits', async () => {
  screenWidth(true)
  const { user } = await openFirst(cases())
  const handle = await resizer()
  expect(handle).toHaveAttribute('aria-orientation', 'vertical')
  expect(handle).toHaveAttribute('aria-valuenow', String(INSPECTOR_LIMITS.default))
  expect(handle).toHaveAttribute('aria-valuemin', '320')
  expect(handle).toHaveAttribute('aria-valuemax', '800')
  expect(await panel()).toHaveStyle({ width: '448px' })

  handle.focus()
  await user.keyboard('{ArrowLeft}{ArrowLeft}')
  expect(handle).toHaveAttribute('aria-valuenow', '480')
  expect(await panel()).toHaveStyle({ width: '480px' })
  await user.keyboard('{ArrowRight}')
  expect(handle).toHaveAttribute('aria-valuenow', '464')
  await user.keyboard('{End}{ArrowLeft}')
  expect(handle).toHaveAttribute('aria-valuenow', '800')
  await user.keyboard('{Home}{ArrowRight}')
  expect(handle).toHaveAttribute('aria-valuenow', '320')
  await user.dblClick(handle)
  expect(handle).toHaveAttribute('aria-valuenow', '448')
  expect(await a11yViolations(await panel())).toEqual([])
})

test('dragging the edge left widens the inspector', async () => {
  screenWidth(true)
  const { user } = await openFirst(cases())
  const handle = await resizer()
  await user.pointer([
    { keys: '[MouseLeft>]', target: handle, coords: { clientX: 600 } },
    { target: handle, coords: { clientX: 500 } },
    { keys: '[/MouseLeft]', target: handle, coords: { clientX: 500 } },
  ])
  expect(handle).toHaveAttribute('aria-valuenow', '548')
  // A move after letting go changes nothing.
  await user.pointer({ target: handle, coords: { clientX: 300 } })
  expect(handle).toHaveAttribute('aria-valuenow', '548')
})

test('the width survives switching cases and a reload, as a number only', async () => {
  screenWidth(true)
  const served = cases()
  const { user, unmount } = await openFirst(served)
  ;(await resizer()).focus()
  await user.keyboard('{ArrowLeft}')
  expect(window.localStorage.getItem(WIDTH_KEY)).toBe('464')

  await user.click(screen.getByRole('link', { name: /Paradas repetidas/ }))
  await screen.findByRole('heading', { level: 1, name: /Paradas repetidas/ })
  expect(await resizer()).toHaveAttribute('aria-valuenow', '464')

  unmount()
  await openFirst(served)
  expect(await resizer()).toHaveAttribute('aria-valuenow', '464')
})

test('the cases list is resized from its right edge too, and remembered', async () => {
  screenWidth(true)
  const served = cases()
  const { user, unmount } = await openFirst(served)
  const handle = await screen.findByRole('separator', { name: 'Resize cases list' })
  const list = screen.getByRole('complementary', { name: 'Cases list' })
  expect(handle).toHaveAttribute('aria-valuenow', '320')
  expect(list).toHaveStyle({ width: '320px' })

  handle.focus()
  await user.keyboard('{ArrowRight}{ArrowRight}')
  expect(handle).toHaveAttribute('aria-valuenow', '352')
  expect(list).toHaveStyle({ width: '352px' })
  await user.keyboard('{ArrowLeft}{Home}{ArrowLeft}')
  expect(handle).toHaveAttribute('aria-valuenow', '240')
  await user.keyboard('{End}')
  expect(handle).toHaveAttribute('aria-valuenow', '560')

  // Dragging right widens it (the opposite of the inspector).
  await user.dblClick(handle)
  await user.pointer([
    { keys: '[MouseLeft>]', target: handle, coords: { clientX: 300 } },
    { target: handle, coords: { clientX: 350 } },
    { keys: '[/MouseLeft]', target: handle, coords: { clientX: 350 } },
  ])
  expect(handle).toHaveAttribute('aria-valuenow', '370')
  expect(window.localStorage.getItem('ayo.chat.cases-width')).toBe('370')

  // Collapsed to the rail, there is nothing to resize; expanded, the width is back.
  await user.click(screen.getByRole('button', { name: 'Hide cases' }))
  expect(screen.queryByRole('separator', { name: 'Resize cases list' })).toBeNull()
  await user.click(screen.getByRole('button', { name: 'Show cases' }))
  expect(await screen.findByRole('separator', { name: 'Resize cases list' })).toHaveAttribute(
    'aria-valuenow',
    '370',
  )

  unmount()
  await openFirst(served)
  expect(await screen.findByRole('separator', { name: 'Resize cases list' })).toHaveAttribute(
    'aria-valuenow',
    '370',
  )
  expect(await a11yViolations(screen.getByRole('complementary', { name: 'Cases list' }))).toEqual(
    [],
  )
})

test('a stored width that is not a usable number gives the default', async () => {
  screenWidth(true)
  window.localStorage.setItem(WIDTH_KEY, '9999')
  window.localStorage.setItem('ayo.chat.cases-width', '12px')
  await openFirst(cases())
  expect(await resizer()).toHaveAttribute('aria-valuenow', '448')
  expect(await screen.findByRole('separator', { name: 'Resize cases list' })).toHaveAttribute(
    'aria-valuenow',
    '320',
  )
})

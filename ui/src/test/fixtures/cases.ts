import type { components } from '@/api/schema'

type CaseListItem = components['schemas']['CaseListItem']

const HOUR = 3600 * 1000

let counter = 0

/** A case as `list_cases` returns it; `hoursAgo` sets `updated_at` from the real clock. */
export function makeCaseItem(
  overrides: Partial<CaseListItem> & { hoursAgo?: number } = {},
): CaseListItem {
  const { hoursAgo = 2, ...fields } = overrides
  counter += 1
  const id = counter.toString(16).padStart(12, '0')
  const updated = new Date(Date.now() - hoursAgo * HOUR).toISOString()
  return {
    case_id: `8d2e4b71-5c3a-4f09-a6e2-${id}`,
    tenant: 'cliente-acme',
    title: 'Merma del 4 % en el envasado de la línea 2',
    phase: 'analyse',
    turns: 9,
    pending_actions: 0,
    overdue_actions: 0,
    created_at: new Date(Date.now() - (hoursAgo + 48) * HOUR).toISOString(),
    updated_at: updated,
    closed_at: null,
    web_session_id: `web-${id}`,
    ...fields,
  }
}

/** A list covering each kind of row. */
export const CASES: CaseListItem[] = [
  makeCaseItem({ hoursAgo: 1 }),
  makeCaseItem({
    tenant: 'planta-norte',
    title: 'Paradas repetidas de la llenadora L3 en el turno de noche',
    phase: 'action',
    turns: 14,
    pending_actions: 3,
    overdue_actions: 1,
    hoursAgo: 5,
  }),
  makeCaseItem({
    tenant: 'planta-sur',
    title: 'Fugas en la junta de la bomba P-201',
    phase: 'closed',
    turns: 21,
    closed_at: new Date(Date.now() - 30 * HOUR).toISOString(),
    hoursAgo: 30,
  }),
  makeCaseItem({
    title: 'Temperatura alta en el horno 2',
    phase: 'challenge',
    turns: 3,
    web_session_id: null,
    hoursAgo: 50,
  }),
  makeCaseItem({ title: null, phase: 'understand', turns: 1, hoursAgo: 80 }),
]

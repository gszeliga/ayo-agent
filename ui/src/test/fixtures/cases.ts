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

type CaseDetail = components['schemas']['CaseDetail']
type CaseTurn = components['schemas']['CaseTurn']
type Phase = CaseDetail['phase']

/** A case as `get_case` returns it, matching `item` (by default the first of `CASES`). */
export function makeCaseDetail(
  item: CaseListItem = CASES[0] ?? makeCaseItem(),
  overrides: Partial<CaseDetail> = {},
): CaseDetail {
  return {
    case_id: item.case_id,
    tenant: item.tenant,
    title: item.title,
    phase: item.phase,
    version: item.turns + 1,
    turns: item.turns,
    created_at: item.created_at,
    updated_at: item.updated_at,
    closed_at: item.closed_at,
    web_session_id: item.web_session_id,
    fields: {
      what: item.title,
      where: 'Línea 2, envasadora',
      since: 'Desde el lunes 9',
      standard: 'Merma máxima del 1 %',
    },
    events: [],
    actions: [],
    summary: null,
    usage: {
      llm_calls: item.turns,
      prompt_tokens: 3000 * item.turns,
      completion_tokens: 330 * item.turns,
      total_tokens: 3330 * item.turns,
      cost: 0.0021 * item.turns,
    },
    ...overrides,
  }
}

/** Turn `turn` of a case: a question and a reply, in `phase` unless `phaseAfter` moves it. */
export function makeTurn(
  turn: number,
  {
    phase = 'analyse',
    phaseAfter,
    reply,
  }: { phase?: Phase; phaseAfter?: Phase; reply?: string } = {},
): CaseTurn {
  const at = new Date(Date.UTC(2026, 10, 12, 9, turn)).toISOString()
  return {
    turn,
    created_at: at,
    phase_before: phase,
    phase_after: phaseAfter ?? phase,
    user_message: {
      content: `Mensaje ${String(turn)} del operario`,
      created_at: at,
      state_at_time: phase,
    },
    reply: {
      content: reply ?? `Respuesta ${String(turn)} del copiloto`,
      created_at: at,
      state_at_time: phaseAfter ?? phase,
    },
    trace: {
      capped: false,
      duration_ms: 2400,
      model: 'openai/gpt-5-mini',
      prompts_version: 'draft-3',
      retrieval_error: null,
      retrieved: [],
      tool_calls: [],
      usage: {
        llm_calls: 1,
        prompt_tokens: 3000,
        completion_tokens: 330,
        total_tokens: 3330,
        cost: 0.0021,
      },
    },
  }
}

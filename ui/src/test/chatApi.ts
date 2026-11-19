import { delay, http, HttpResponse } from 'msw'

import type { components } from '@/api/schema'

import { makeCaseDetail, makeCaseItem, makeTurn } from './fixtures/cases'
import { TENANTS } from './fixtures/documents'
import { API } from './render'
import { server } from './server'

type CaseDetail = components['schemas']['CaseDetail']
type CaseListItem = components['schemas']['CaseListItem']
type CaseTurn = components['schemas']['CaseTurn']

export interface ServedCase {
  detail: CaseDetail
  turns: CaseTurn[]
}

export interface SentMessage {
  session_id: string
  tenant: string
  text: string
}

/** A case and its turns as the stand-in API holds them. */
export function servedCase(item: CaseListItem = makeCaseItem()): ServedCase {
  const detail = makeCaseDetail(item)
  return {
    detail,
    turns: Array.from({ length: detail.turns }, (_, i) => makeTurn(i + 1, { phase: item.phase })),
  }
}

function listItem({ detail }: ServedCase): CaseListItem {
  return makeCaseItem({
    case_id: detail.case_id,
    tenant: detail.tenant,
    title: detail.title,
    phase: detail.phase,
    turns: detail.turns,
    closed_at: detail.closed_at,
    web_session_id: detail.web_session_id,
  })
}

/**
 * Stands in for the API the chat uses: tenants, the list, each case and its turns, and
 * `POST /copilot/messages`, which stores a turn (opening a case for a new session) and
 * answers. `gate`, when set, holds each message's answer until it resolves.
 */
export function serveChat(cases: ServedCase[]) {
  const sent: SentMessage[] = []
  const turnQueries: string[] = []
  let listCalls = 0
  let caseCalls = 0
  const control: { gate: Promise<undefined> | null } = { gate: null }
  const find = (id: unknown) => cases.find((c) => c.detail.case_id === id)

  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.json(TENANTS)),
    http.get(`${API}/admin/cases`, () => {
      listCalls += 1
      const items = cases.map(listItem)
      return HttpResponse.json({ items, total: items.length, limit: 20, offset: 0 })
    }),
    http.get(`${API}/admin/cases/:caseId`, ({ params }) => {
      caseCalls += 1
      const found = find(params.caseId)
      return found
        ? HttpResponse.json(found.detail)
        : HttpResponse.json(
            { detail: [{ type: 'case_not_found', loc: ['path', 'case_id'], msg: 'No case.' }] },
            { status: 404 },
          )
    }),
    http.get(`${API}/admin/cases/:caseId/turns`, ({ params, request }) => {
      const query = new URL(request.url).searchParams
      turnQueries.push(query.toString())
      const turns = find(params.caseId)?.turns ?? []
      const offset = Number(query.get('offset'))
      const limit = Number(query.get('limit'))
      return HttpResponse.json({
        items: turns.slice(offset, offset + limit),
        total: turns.length,
        limit,
        offset,
      })
    }),
    http.post(`${API}/copilot/messages`, async ({ request }) => {
      const body = (await request.json()) as SentMessage
      sent.push(body)
      if (control.gate) await control.gate
      await delay(1)
      let found = cases.find((c) => c.detail.web_session_id === body.session_id)
      if (!found) {
        found = servedCase(
          makeCaseItem({
            tenant: body.tenant,
            title: null,
            phase: 'understand',
            turns: 0,
            web_session_id: body.session_id,
          }),
        )
        found.turns = []
        cases.unshift(found)
      }
      const number = found.turns.length + 1
      const phase = found.detail.phase
      const base = makeTurn(number, { phase, reply: `Entendido: ${body.text}` })
      const turn = { ...base, user_message: { ...base.user_message, content: body.text } }
      found.turns.push(turn)
      found.detail = { ...found.detail, turns: number, version: found.detail.version + 1 }
      return HttpResponse.json({
        session_id: body.session_id,
        case_id: found.detail.case_id,
        turn: number,
        reply: turn.reply.content,
        phase,
        previous_phase: phase,
        phase_changed: false,
        tools_used: [],
      })
    }),
  )
  return {
    sent,
    turnQueries,
    control,
    listCalls: () => listCalls,
    caseCalls: () => caseCalls,
  }
}

/** A promise and the function that resolves it. */
export function deferred(): { promise: Promise<undefined>; resolve: () => void } {
  let release: (value: undefined) => void = () => undefined
  const promise = new Promise<undefined>((done) => {
    release = done
  })
  return {
    promise,
    resolve: () => {
      release(undefined)
    },
  }
}

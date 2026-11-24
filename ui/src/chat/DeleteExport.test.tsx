import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { CASES, makeTurn } from '@/test/fixtures/cases'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { downloadFile } from './download'

vi.mock('./download', () => ({ downloadFile: vi.fn() }))

const location = () => screen.getByTestId('location').textContent
const casesList = () => screen.getByRole('complementary', { name: 'Cases list' })

function chatCases(): ServedCase[] {
  return CASES.map((item) => servedCase(item))
}

/** The stand-in API, plus a delete that removes the case (or answers `status`). */
function serve(cases: ServedCase[], deleteStatus?: number) {
  const api = serveChat(cases)
  const deleted: string[] = []
  server.use(
    http.delete(`${API}/admin/cases/:caseId`, ({ params }) => {
      deleted.push(String(params.caseId))
      if (deleteStatus !== undefined) {
        return HttpResponse.json(
          { detail: [{ type: 'internal', loc: [], msg: 'The API failed.' }] },
          { status: deleteStatus },
        )
      }
      const index = cases.findIndex((c) => c.detail.case_id === params.caseId)
      if (index < 0) {
        return HttpResponse.json(
          { detail: [{ type: 'case_not_found', loc: [], msg: 'No case.' }] },
          { status: 404 },
        )
      }
      cases.splice(index, 1)
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return { api, deleted }
}

async function open(served: ServedCase) {
  const rendered = renderApp(`/chat/${served.detail.case_id}`, { connected: true })
  await screen.findByRole('heading', { level: 1 })
  return rendered
}

afterEach(() => {
  vi.mocked(downloadFile).mockClear()
})

test('delete says what goes, Cancel keeps it, Delete removes it and returns to /chat', async () => {
  const cases = chatCases()
  const first = cases[0]
  if (!first) throw new Error('no case')
  first.detail = {
    ...first.detail,
    events: [
      {
        id: 1,
        event_type: 'evidence',
        content: 'x',
        state_at_time: 'challenge',
        created_at: '2026-11-12T09:00:00Z',
      },
    ],
  }
  const title = first.detail.title ?? ''
  const { deleted } = serve(cases)
  const { user } = await open(first)
  expect(within(casesList()).getByText(title)).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  let dialog = await screen.findByRole('alertdialog', { name: 'Delete this case?' })
  expect(dialog).toHaveTextContent(
    'It is removed for good, with everything it holds: 9 turns (messages, replies and traces), 1 annotation, 0 actions. There is no undo.',
  )
  expect(dialog).toHaveTextContent(
    'A later message on this conversation’s session starts a new case.'.replace('’', "'"),
  )
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => {
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })
  expect(deleted).toEqual([])

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  dialog = await screen.findByRole('alertdialog')
  await user.click(within(dialog).getByRole('button', { name: 'Delete case' }))

  await waitFor(() => {
    expect(location()).toBe('/chat')
  })
  expect(deleted).toEqual([first.detail.case_id])
  expect(await screen.findByText('Case deleted')).toBeVisible()
  expect(await screen.findByRole('heading', { name: 'Pick a case' })).toBeVisible()
  await waitFor(() => {
    expect(within(casesList()).queryByText(title)).toBeNull()
  })
  // Many steps (two dialogs, typing, a navigation): about 1.7 s alone, near the default 5 s
  // when every file runs at once.
}, 15_000)

test('a case already deleted counts as deleted', async () => {
  const cases = chatCases()
  const first = cases[0]
  if (!first) throw new Error('no case')
  serve(cases)
  const { user } = await open(first)
  cases.splice(0, 1) // gone meanwhile, elsewhere

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete case' }),
  )

  expect(await screen.findByText('The case was already deleted')).toBeVisible()
  await waitFor(() => {
    expect(location()).toBe('/chat')
  })
})

test('a failed delete keeps the dialog open with the reason', async () => {
  const cases = chatCases()
  const first = cases[0]
  if (!first) throw new Error('no case')
  serve(cases, 500)
  const { user } = await open(first)

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog')
  await user.click(within(dialog).getByRole('button', { name: 'Delete case' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent('The API failed.')
  expect(location()).toBe(`/chat/${first.detail.case_id}`)
  expect(within(dialog).getByRole('button', { name: 'Delete case' })).toBeEnabled()
})

test('a read-only case can be exported and deleted too', async () => {
  const cases = chatCases()
  const other = cases[3] // another channel
  if (!other) throw new Error('no case')
  serve(cases)
  const { user } = await open(other)
  expect(screen.getByRole('button', { name: 'Export' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: 'Delete' }))
  const dialog = await screen.findByRole('alertdialog')
  expect(dialog).not.toHaveTextContent('starts a new case')
})

test('export fetches the turns not loaded yet, previews and downloads the whole case', async () => {
  const cases = chatCases()
  const first = cases[0]
  if (!first) throw new Error('no case')
  first.turns = Array.from({ length: 45 }, (_, i) => makeTurn(i + 1))
  first.detail = { ...first.detail, turns: 45 }
  const { api } = serve(cases)
  const { user } = await open(first)
  const log = await screen.findByRole('log', { name: 'Conversation' })
  await waitFor(() => {
    expect(within(log).getAllByRole('listitem', { name: /^Turn \d+$/ })).toHaveLength(20)
  })
  api.turnQueries.length = 0

  await user.click(screen.getByRole('button', { name: 'Export' }))
  const dialog = await screen.findByRole('dialog', { name: 'Export the case' })
  const preview = await within(dialog).findByLabelText('Preview')
  expect(api.turnQueries).toEqual(['offset=0&limit=25'])
  for (const n of [1, 25, 26, 45]) expect(preview).toHaveTextContent(`### Turn ${String(n)} ·`)
  expect(preview.textContent.match(/### Turn \d+ ·/g)).toHaveLength(45)

  await user.click(within(dialog).getByRole('button', { name: 'Download' }))
  expect(downloadFile).toHaveBeenCalledWith(
    expect.stringMatching(/^case-8d2e4b71-\d{8}\.md$/),
    preview.textContent,
    'text/markdown;charset=utf-8',
  )

  await user.click(within(dialog).getByRole('button', { name: 'JSON' }))
  expect(within(dialog).getByRole('button', { name: 'JSON' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  const json = JSON.parse(within(dialog).getByLabelText('Preview').textContent) as {
    turns: { turn: number }[]
  }
  expect(json.turns.map((t) => t.turn)).toEqual(Array.from({ length: 45 }, (_, i) => i + 1))
  await user.click(within(dialog).getByRole('button', { name: 'Download' }))
  expect(downloadFile).toHaveBeenLastCalledWith(
    expect.stringMatching(/\.json$/),
    expect.stringContaining('"exported_at"'),
    'application/json',
  )

  // The conversation's paging is untouched: still the latest 20, then Load earlier turns.
  await user.keyboard('{Escape}')
  expect(within(log).getAllByRole('listitem', { name: /^Turn \d+$/ })).toHaveLength(20)
  expect(screen.getByRole('button', { name: 'Load earlier turns' })).toBeVisible()
})

test('a failed read offers Retry and downloads nothing', async () => {
  const cases = chatCases()
  const first = cases[0]
  if (!first) throw new Error('no case')
  first.turns = Array.from({ length: 30 }, (_, i) => makeTurn(i + 1))
  first.detail = { ...first.detail, turns: 30 }
  serve(cases)
  const { user } = await open(first)
  await screen.findAllByRole('listitem', { name: /^Turn \d+$/ })
  let fail = true
  server.use(
    http.get(`${API}/admin/cases/:caseId/turns`, ({ request }) => {
      const query = new URL(request.url).searchParams
      if (fail) {
        return HttpResponse.json(
          { detail: [{ type: 'internal', loc: [], msg: 'The API failed.' }] },
          { status: 500 },
        )
      }
      const offset = Number(query.get('offset'))
      const limit = Number(query.get('limit'))
      return HttpResponse.json({
        items: first.turns.slice(offset, offset + limit),
        total: first.turns.length,
        limit,
        offset,
      })
    }),
  )

  await user.click(screen.getByRole('button', { name: 'Export' }))
  const dialog = await screen.findByRole('dialog', { name: 'Export the case' })
  expect(await within(dialog).findByRole('button', { name: 'Retry' })).toBeVisible()
  expect(within(dialog).getByRole('button', { name: 'Download' })).toBeDisabled()
  expect(downloadFile).not.toHaveBeenCalled()

  fail = false
  await user.click(within(dialog).getByRole('button', { name: 'Retry' }))
  expect(await within(dialog).findByLabelText('Preview')).toHaveTextContent('### Turn 1 ·')
})

describe('in Spanish', () => {
  test('the delete dialog says what goes, and the toast, in Spanish', async () => {
    const cases = chatCases()
    const first = cases[0]
    if (!first) throw new Error('no case')
    first.detail = {
      ...first.detail,
      summary: {
        content: '**Problema:** merma en la línea 2.',
        model: 'test/model',
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
    }
    serve(cases)
    const { user } = renderApp(`/chat/${first.detail.case_id}`, {
      connected: true,
      language: 'es',
    })
    await screen.findByRole('heading', { level: 1 })

    await user.click(screen.getByRole('button', { name: 'Eliminar' }))
    const dialog = await screen.findByRole('alertdialog', { name: '¿Eliminar este caso?' })
    expect(dialog).toHaveTextContent(
      'Se elimina para siempre, con todo lo que contiene: 9 turnos (mensajes, respuestas y trazas), 0 anotaciones, 0 acciones y su resumen de IA. No se puede deshacer.',
    )
    expect(dialog).toHaveTextContent(
      'Un mensaje posterior en la sesión de esta conversación abre un caso nuevo.',
    )
    expect(within(dialog).getByRole('button', { name: 'Cancelar' })).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar caso' }))

    expect(await screen.findByText('Caso eliminado')).toBeVisible()
    await waitFor(() => {
      expect(location()).toBe('/chat')
    })
  })

  test('an already deleted case and a failure are Spanish; the API message as received', async () => {
    const cases = chatCases()
    const first = cases[0]
    if (!first) throw new Error('no case')
    serve(cases, 500)
    const { user } = renderApp(`/chat/${first.detail.case_id}`, {
      connected: true,
      language: 'es',
    })
    await screen.findByRole('heading', { level: 1 })

    await user.click(screen.getByRole('button', { name: 'Eliminar' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar caso' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('The API failed.')

    server.use(
      http.delete(`${API}/admin/cases/:caseId`, () =>
        HttpResponse.json(
          { detail: [{ type: 'case_not_found', loc: [], msg: 'No case.' }] },
          { status: 404 },
        ),
      ),
    )
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar caso' }))
    expect(await screen.findByText('El caso ya estaba eliminado')).toBeVisible()
  })
})

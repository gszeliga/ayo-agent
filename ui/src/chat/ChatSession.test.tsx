import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { a11yViolations } from '@/test/axe'
import { serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { CASES } from '@/test/fixtures/cases'
import { makeSettings } from '@/test/fixtures/services'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

import { downloadFile } from './download'
import { WIDE_QUERY } from './inspectorState'

vi.mock('./download', () => ({ downloadFile: vi.fn() }))

beforeEach(() => {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query === WIDE_QUERY,
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  )
})
afterEach(() => {
  vi.restoreAllMocks()
})

const location = () => screen.getByTestId('location').textContent
/** What the chat may keep in browser storage: names and numbers, never conversation text. */
const CHAT_KEYS = ['ayo.chat.cases-width', 'ayo.chat.inspector-width', 'ayo.chat.last-tenant']

function serve(): ServedCase[] {
  const cases = CASES.map((item) => servedCase(item))
  serveChat(cases)
  server.use(
    http.get(`${API}/admin/settings`, () => HttpResponse.json(makeSettings())),
    http.post(`${API}/admin/cases/:caseId/summary`, ({ params }) => {
      const found = cases.find((c) => c.detail.case_id === params.caseId)
      if (!found) return HttpResponse.json({ detail: [] }, { status: 404 })
      const made = {
        content: 'Resumen confidencial del caso',
        model: 'openai/gpt-5-mini',
        generated_at: new Date().toISOString(),
        source_version: found.detail.version,
        stale: false,
        usage: {
          llm_calls: 1,
          prompt_tokens: null,
          completion_tokens: null,
          total_tokens: 900,
          cost: 0.001,
        },
      }
      found.detail = { ...found.detail, summary: made }
      return HttpResponse.json(made)
    }),
  )
  return cases
}

test('a whole session keeps nothing of the conversations in browser storage', async () => {
  serve()
  const { user } = renderApp('/chat', { connected: true })

  // A new conversation and a message.
  await user.click(await screen.findByRole('button', { name: 'New conversation' }))
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByRole('combobox', { name: 'Tenant' })
  await user.click(within(dialog).getByRole('button', { name: 'Start' }))
  await user.type(
    await screen.findByRole('textbox', { name: 'Message' }),
    'Texto confidencial de planta{Enter}',
  )
  await waitFor(() => {
    expect(location()).toMatch(/^\/chat\/[0-9a-f-]{36}$/)
  })
  const inspector = await screen.findByRole('complementary', { name: 'Inspector' })

  // Every tab, both resizes, a summary and an export.
  for (const tab of ['Actions', 'Trace', 'State']) {
    await user.click(within(inspector).getByRole('tab', { name: tab }))
  }
  screen.getByRole('separator', { name: 'Resize inspector' }).focus()
  await user.keyboard('{ArrowLeft}')
  screen.getByRole('separator', { name: 'Resize cases list' }).focus()
  await user.keyboard('{ArrowRight}')
  await user.click(within(inspector).getByRole('tab', { name: 'Summary' }))
  await user.click(await within(inspector).findByRole('button', { name: 'Generate AI summary' }))
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Generate' }),
  )
  expect(await within(inspector).findByText('Resumen confidencial del caso')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Export' }))
  const exporting = await screen.findByRole('dialog', { name: 'Export the case' })
  await within(exporting).findByLabelText('Preview')
  await user.click(within(exporting).getByRole('button', { name: 'Download' }))
  expect(downloadFile).toHaveBeenCalledTimes(1)

  const local = Object.keys(window.localStorage).sort()
  expect(local.every((key) => CHAT_KEYS.includes(key) || !key.startsWith('ayo.chat'))).toBe(true)
  expect(local.filter((key) => key.startsWith('ayo.chat'))).toEqual(CHAT_KEYS)
  // Only the connection (session storage, as before this milestone) outside the chat's keys.
  expect(Object.keys(window.sessionStorage)).toEqual(['ayo.connection'])
  const stored = [window.localStorage, window.sessionStorage].flatMap((storage) =>
    Object.keys(storage).map((key) => `${key}=${storage.getItem(key) ?? ''}`),
  )
  expect(stored.join('\n')).not.toMatch(
    /confidencial|Entendido|Resumen|Merma|Respuesta|Mensaje|Texto/,
  )
  expect(window.localStorage.getItem('ayo.chat.inspector-width')).toMatch(/^\d+$/)
  expect(window.localStorage.getItem('ayo.chat.cases-width')).toMatch(/^\d+$/)
  expect(document.cookie).toBe('')
  // A whole session, step by step: well past the default 5 s when every file runs at once.
}, 15_000)

test('the chat page has no accessibility violations, nor its dialogs', async () => {
  const cases = serve()
  const first = cases[0]
  if (!first) throw new Error('no case')
  const { user } = renderApp(`/chat/${first.detail.case_id}`, { connected: true })
  await screen.findAllByRole('listitem', { name: /^Turn \d+$/ })
  await screen.findByRole('complementary', { name: 'Inspector' })
  expect(await a11yViolations()).toEqual([])

  await user.click(screen.getByRole('button', { name: 'Export' }))
  const exporting = await screen.findByRole('dialog', { name: 'Export the case' })
  await within(exporting).findByLabelText('Preview')
  expect(await a11yViolations(exporting)).toEqual([])
  await user.keyboard('{Escape}')
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  await user.click(screen.getByRole('button', { name: 'Delete' }))
  expect(await a11yViolations(await screen.findByRole('alertdialog'))).toEqual([])
})

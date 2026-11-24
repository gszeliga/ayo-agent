import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { CASES } from '@/test/fixtures/cases'
import { deferred, serveChat, servedCase, type ServedCase } from '@/test/chatApi'
import { API, renderApp } from '@/test/render'
import { server } from '@/test/server'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

const location = () => screen.getByTestId('location').textContent
const messageBox = () => screen.findByRole('textbox', { name: 'Message' })
const turnItems = async () =>
  within(await screen.findByRole('log', { name: 'Conversation' })).findAllByRole('listitem', {
    name: /^Turn \d+$/,
  })

function errorBody(status: number, type: string, msg: string) {
  return HttpResponse.json({ detail: [{ type, loc: ['body'], msg }] }, { status })
}

/** An open web case (the first fixture, 9 turns) and the other fixtures. */
function chatCases(): ServedCase[] {
  return CASES.map((item) => servedCase(item))
}

async function openCase(served: ServedCase) {
  const rendered = renderApp(`/chat/${served.detail.case_id}`, { connected: true })
  await turnItems()
  return rendered
}

test('a new conversation asks the tenant, then the first reply opens its case', async () => {
  window.localStorage.setItem('ayo.chat.last-tenant', 'planta-sur')
  const api = serveChat(chatCases())
  const { user } = renderApp('/chat', { connected: true })

  await user.click(await screen.findByRole('button', { name: 'New conversation' }))
  const dialog = await screen.findByRole('dialog', { name: 'New conversation' })
  const tenant = await within(dialog).findByRole('combobox', { name: 'Tenant' })
  expect(tenant).toHaveValue('planta-sur')
  await user.selectOptions(tenant, 'planta-norte')
  await user.click(within(dialog).getByRole('button', { name: 'Start' }))

  await waitFor(() => {
    expect(location()).toBe('/chat/new')
  })
  const heading = await screen.findByRole('heading', { level: 1, name: 'New conversation' })
  expect(heading.closest('header')).toHaveTextContent('planta-norte')
  expect(window.localStorage.getItem('ayo.chat.last-tenant')).toBe('planta-norte')

  await user.type(await messageBox(), 'La línea 3 se para cada noche{Enter}')

  await waitFor(() => {
    expect(location()).toMatch(/^\/chat\/[0-9a-f-]+$/)
  })
  expect(location()).not.toBe('/chat/new')
  expect(api.sent).toHaveLength(1)
  expect(api.sent[0]).toEqual({
    session_id: expect.stringMatching(UUID_V4) as string,
    tenant: 'planta-norte',
    text: 'La línea 3 se para cada noche',
  })
  const [turn] = await turnItems()
  expect(turn).toHaveTextContent('La línea 3 se para cada noche')
  expect(await within(turn ?? document.body).findByText(/Entendido/)).toBeInTheDocument()
  // A dialog, typing, a send and a navigation: about 1.8 s alone, 4.2 s when every file runs
  // at once (near the default 5 s).
}, 15_000)

test('the dialog preselects the first tenant when none was used, and can be cancelled', async () => {
  serveChat(chatCases())
  const { user } = renderApp('/chat', { connected: true })

  await user.click(await screen.findByRole('button', { name: 'New conversation' }))
  const dialog = await screen.findByRole('dialog')
  expect(await within(dialog).findByRole('combobox', { name: 'Tenant' })).toHaveValue(
    'planta-norte',
  )
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(location()).toBe('/chat')
  expect(window.localStorage.getItem('ayo.chat.last-tenant')).toBeNull()
})

test('the collapsed rail can start a new conversation too', async () => {
  serveChat(chatCases())
  const { user } = renderApp('/chat', { connected: true })

  await user.click(await screen.findByRole('button', { name: 'Hide cases' }))
  await user.click(screen.getByRole('button', { name: 'New conversation' }))

  expect(await screen.findByRole('dialog', { name: 'New conversation' })).toBeInTheDocument()
})

test('/chat/new without a draft offers to start one', async () => {
  serveChat(chatCases())
  const { user } = renderApp('/chat/new', { connected: true })

  expect(
    await screen.findByRole('heading', { name: 'Start a new conversation' }),
  ).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Message' })).not.toBeInTheDocument()
  const main = screen.getByRole('heading', { name: 'Start a new conversation' }).closest('section')
  await user.click(within(main ?? document.body).getByRole('button', { name: 'New conversation' }))

  expect(await screen.findByRole('dialog', { name: 'New conversation' })).toBeInTheDocument()
})

test('a reply on an open case: its session, then the case and the new turn alone', async () => {
  const cases = chatCases()
  const served = cases[0] as ServedCase
  const api = serveChat(cases)
  const { user } = await openCase(served)
  const listCalls = api.listCalls()
  const caseCalls = api.caseCalls()

  await user.type(await messageBox(), '  Desde el lunes  ')
  await user.click(screen.getByRole('button', { name: 'Send' }))

  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(10)
  })
  expect(api.sent).toEqual([
    { session_id: served.detail.web_session_id, tenant: 'cliente-acme', text: 'Desde el lunes' },
  ])
  expect(api.turnQueries.at(-1)).toBe('offset=9&limit=1')
  expect((await turnItems()).at(-1)).toHaveTextContent('Desde el lunes')
  await waitFor(() => {
    expect(screen.getByTestId('case-facts')).toHaveTextContent('10 turns')
  })
  expect(api.caseCalls()).toBeGreaterThan(caseCalls)
  await waitFor(() => {
    expect(api.listCalls()).toBeGreaterThan(listCalls)
  })
  expect(await messageBox()).toHaveValue('')
  expect(screen.queryByTestId('pending-turn')).not.toBeInTheDocument()
})

test('Enter sends, Shift+Enter adds a line, an empty message is not sent', async () => {
  const cases = chatCases()
  const api = serveChat(cases)
  const { user } = await openCase(cases[0] as ServedCase)
  const box = await messageBox()

  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  await user.type(box, '   {Enter}')
  expect(api.sent).toHaveLength(0)

  await user.clear(box)
  await user.type(box, 'Primera línea{Shift>}{Enter}{/Shift}segunda')
  expect(box).toHaveValue('Primera línea\nsegunda')
  expect(api.sent).toHaveLength(0)

  await user.type(box, '{Enter}')
  await waitFor(() => {
    expect(api.sent).toEqual([expect.objectContaining({ text: 'Primera línea\nsegunda' })])
  })
})

test('while a turn runs: the message as sending, a typing indicator, the input disabled', async () => {
  const cases = chatCases()
  const api = serveChat(cases)
  const gate = deferred()
  api.control.gate = gate.promise
  const { user } = await openCase(cases[0] as ServedCase)

  await user.type(await messageBox(), 'Tengo fotos de la junta{Enter}')

  const pending = await screen.findByTestId('pending-turn')
  expect(pending).toHaveTextContent('Tengo fotos de la junta')
  expect(pending).toHaveTextContent('Sending…')
  expect(within(pending).getByRole('status')).toHaveTextContent('The copilot is answering')
  expect(await messageBox()).toBeDisabled()
  expect(await messageBox()).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

  gate.resolve()

  await waitFor(() => {
    expect(screen.queryByTestId('pending-turn')).not.toBeInTheDocument()
  })
  expect((await turnItems()).at(-1)).toHaveTextContent('Tengo fotos de la junta')
  expect(await messageBox()).toBeEnabled()
})

test.each([
  [409, 'case_changed', 'Another message in this conversation was saved', 'Reload case'],
  [409, 'case_closed', 'This case is closed', 'Reload case'],
  [422, 'tenant_mismatch', 'The API refused the message: tenant does not match', null],
  [502, 'llm_unavailable', 'The language model failed, so nothing was stored', 'Send again'],
  [503, 'llm_not_configured', 'no language model configured', null],
])('a %d %s keeps the text and stores nothing', async (status, type, text, action) => {
  const cases = chatCases()
  serveChat(cases)
  server.use(
    http.post(`${API}/copilot/messages`, () =>
      errorBody(status, type, type === 'tenant_mismatch' ? 'tenant does not match' : 'failed'),
    ),
  )
  const { user } = await openCase(cases[0] as ServedCase)

  await user.type(await messageBox(), 'Mensaje que falla{Enter}')

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(text)
  expect(await messageBox()).toHaveValue('Mensaje que falla')
  expect(await messageBox()).toBeEnabled()
  expect(screen.queryByTestId('pending-turn')).not.toBeInTheDocument()
  expect(await turnItems()).toHaveLength(9)
  for (const name of ['Send again', 'Reload case']) {
    const button = within(alert).queryByRole('button', { name })
    if (name === action) expect(button).toBeInTheDocument()
    else expect(button).not.toBeInTheDocument()
  }
})

test('a network failure keeps the text and offers to send again, which works', async () => {
  const cases = chatCases()
  const api = serveChat(cases)
  let fail = true
  server.use(http.post(`${API}/copilot/messages`, () => (fail ? HttpResponse.error() : undefined)))
  const { user } = await openCase(cases[0] as ServedCase)

  await user.type(await messageBox(), 'Otra vez{Enter}')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent("Can't reach the API")
  expect(await messageBox()).toHaveValue('Otra vez')

  fail = false
  await user.click(within(alert).getByRole('button', { name: 'Send again' }))

  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(10)
  })
  expect(api.sent.map((m) => m.text)).toEqual(['Otra vez'])
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('Reload case after a conflict reads the case again and clears the error', async () => {
  const cases = chatCases()
  const api = serveChat(cases)
  server.use(http.post(`${API}/copilot/messages`, () => errorBody(409, 'case_changed', 'changed')))
  const { user } = await openCase(cases[0] as ServedCase)
  await user.type(await messageBox(), 'Choca{Enter}')
  const alert = await screen.findByRole('alert')
  const before = api.caseCalls()

  await user.click(within(alert).getByRole('button', { name: 'Reload case' }))

  await waitFor(() => {
    expect(api.caseCalls()).toBe(before + 1)
  })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(await messageBox()).toHaveValue('Choca')
})

test('a read-only case has no message box', async () => {
  const cases = chatCases()
  serveChat(cases)
  renderApp(`/chat/${(cases[3] as ServedCase).detail.case_id}`, { connected: true })

  await turnItems()
  expect(screen.queryByRole('textbox', { name: 'Message' })).not.toBeInTheDocument()
  expect(screen.getByText(/came from another channel/)).toBeInTheDocument()
})

test('leaving a case mid-turn: no alert elsewhere, and the turn is there on coming back', async () => {
  const cases = chatCases()
  const first = cases[0] as ServedCase
  const api = serveChat(cases)
  const gate = deferred()
  api.control.gate = gate.promise
  const { user } = await openCase(first)
  await user.type(await messageBox(), 'Me voy a otro caso{Enter}')
  await screen.findByTestId('pending-turn')

  const list = screen.getByRole('list', { name: 'Cases' })
  await user.click(within(list).getAllByRole('link')[1] ?? document.body)
  await screen.findByRole('heading', { level: 1, name: /Paradas repetidas/ })
  gate.resolve()
  await waitFor(() => {
    expect(first.turns).toHaveLength(10)
  })

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByTestId('pending-turn')).not.toBeInTheDocument()
  await user.click(within(list).getAllByRole('link')[0] ?? document.body)
  await waitFor(async () => {
    expect(await turnItems()).toHaveLength(10)
  })
  expect((await turnItems()).at(-1)).toHaveTextContent('Me voy a otro caso')
})

test('a failure after leaving the case shows nowhere', async () => {
  const cases = chatCases()
  const api = serveChat(cases)
  const gate = deferred()
  api.control.gate = gate.promise
  server.use(
    http.post(`${API}/copilot/messages`, async () => {
      await gate.promise
      return errorBody(502, 'llm_unavailable', 'failed')
    }),
  )
  const { user } = await openCase(cases[0] as ServedCase)
  await user.type(await messageBox(), 'Se pierde{Enter}')
  await screen.findByTestId('pending-turn')

  const list = screen.getByRole('list', { name: 'Cases' })
  await user.click(within(list).getAllByRole('link')[1] ?? document.body)
  await screen.findByRole('heading', { level: 1, name: /Paradas repetidas/ })
  gate.resolve()
  await new Promise((done) => setTimeout(done, 50))

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('nothing of the conversation reaches browser storage, only the tenant name', async () => {
  const cases = chatCases()
  serveChat(cases)
  const { user } = renderApp('/chat', { connected: true })
  await user.click(await screen.findByRole('button', { name: 'New conversation' }))
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByRole('combobox', { name: 'Tenant' })
  await user.click(within(dialog).getByRole('button', { name: 'Start' }))
  await user.type(await messageBox(), 'Texto confidencial de planta{Enter}')
  await waitFor(() => {
    expect(location()).not.toBe('/chat/new')
  })
  await turnItems()

  const stored = [window.localStorage, window.sessionStorage].flatMap((storage) =>
    Object.keys(storage).map((key) => `${key}=${storage.getItem(key) ?? ''}`),
  )
  expect(stored.join('\n')).not.toMatch(/confidencial|Entendido|Merma|Respuesta|Mensaje/)
  expect(Object.keys(window.localStorage)).toEqual(['ayo.chat.last-tenant'])
  expect(document.cookie).toBe('')
})

describe('in Spanish', () => {
  const messageBoxEs = () => screen.findByRole('textbox', { name: 'Mensaje' })
  const turnItemsEs = async () =>
    within(await screen.findByRole('log', { name: 'Conversación' })).findAllByRole('listitem', {
      name: /^Turno \d+$/,
    })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function openCaseEs(served: ServedCase) {
    const rendered = renderApp(`/chat/${served.detail.case_id}`, {
      connected: true,
      language: 'es',
    })
    await turnItemsEs()
    return rendered
  }

  test('while a turn runs: sending and the typing indicator are Spanish', async () => {
    const cases = chatCases()
    const api = serveChat(cases)
    const gate = deferred()
    api.control.gate = gate.promise
    const { user } = await openCaseEs(cases[0] as ServedCase)

    await user.type(await messageBoxEs(), 'Tengo fotos de la junta{Enter}')

    const pending = await screen.findByTestId('pending-turn')
    expect(pending).toHaveTextContent('Usuario: Tengo fotos de la junta')
    expect(pending).toHaveTextContent('Enviando…')
    expect(within(pending).getByRole('status')).toHaveTextContent('El copiloto está respondiendo')
    gate.resolve()
    await waitFor(() => {
      expect(screen.queryByTestId('pending-turn')).not.toBeInTheDocument()
    })
  })

  test.each([
    [409, 'case_changed', 'Se ha guardado otro mensaje de esta conversación', 'Recargar el caso'],
    [409, 'case_closed', 'Este caso está cerrado: no admite más mensajes.', 'Recargar el caso'],
    // The API's own message, as received.
    [422, 'tenant_mismatch', 'La API ha rechazado el mensaje: tenant does not match', null],
    [502, 'llm_unavailable', 'El modelo de lenguaje ha fallado', 'Volver a enviar'],
    [503, 'llm_not_configured', 'ningún modelo de lenguaje configurado', null],
  ])('a %d %s is said in Spanish', async (status, type, text, action) => {
    const cases = chatCases()
    serveChat(cases)
    server.use(
      http.post(`${API}/copilot/messages`, () =>
        errorBody(status, type, type === 'tenant_mismatch' ? 'tenant does not match' : 'failed'),
      ),
    )
    const { user } = await openCaseEs(cases[0] as ServedCase)

    await user.type(await messageBoxEs(), 'Mensaje que falla{Enter}')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(text)
    for (const name of ['Volver a enviar', 'Recargar el caso']) {
      const button = within(alert).queryByRole('button', { name })
      if (name === action) expect(button).toBeInTheDocument()
      else expect(button).not.toBeInTheDocument()
    }
  })

  test('a network failure is said in Spanish, and rewords when the browser switches', async () => {
    const cases = chatCases()
    serveChat(cases)
    server.use(http.post(`${API}/copilot/messages`, () => HttpResponse.error()))
    let browser = ['es-ES']
    vi.spyOn(navigator, 'languages', 'get').mockImplementation(() => browser)
    const { user } = renderApp(`/chat/${(cases[0] as ServedCase).detail.case_id}`, {
      connected: true,
    })
    await turnItemsEs()

    await user.type(await messageBoxEs(), 'Otra vez{Enter}')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/^No se puede conectar con la API/)
    expect(within(alert).getByRole('button', { name: 'Volver a enviar' })).toBeInTheDocument()

    browser = ['en-GB']
    act(() => {
      window.dispatchEvent(new Event('languagechange'))
    })
    expect(screen.getByRole('alert')).toHaveTextContent(/^Can't reach the API/)
    expect(screen.getByRole('button', { name: 'Send again' })).toBeInTheDocument()
  })
})

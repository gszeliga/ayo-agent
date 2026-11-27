import { act, screen, within } from '@testing-library/react'

import { LANGUAGE_KEY } from '@/lib/language'
import { openConnectionMenu, renderApp } from '@/test/render'

/** The browser's preferred languages; `set` fires `languagechange` like the browser would. */
function browserLanguages(initial: string[]) {
  let current = initial
  vi.spyOn(navigator, 'languages', 'get').mockImplementation(() => current)
  return {
    set: (next: string[]) => {
      current = next
      act(() => {
        window.dispatchEvent(new Event('languagechange'))
      })
    },
  }
}

const nav = () => screen.getByRole('navigation', { name: /^(Main|Principal)$/ })

afterEach(() => {
  vi.restoreAllMocks()
})

test('Español in the connection menu turns the shell Spanish, sets lang and is kept', async () => {
  browserLanguages(['en-GB'])
  const { user } = renderApp('/settings', { connected: true })
  expect(document.documentElement.lang).toBe('en')

  await openConnectionMenu(user)
  await user.click(screen.getByRole('menuitemradio', { name: 'Español' }))

  expect(within(nav()).getByRole('link', { name: 'Documentos' })).toBeInTheDocument()
  expect(within(nav()).getByRole('link', { name: 'Búsqueda' })).toBeInTheDocument()
  expect(within(nav()).getByRole('link', { name: 'Ajustes de indexación' })).toBeInTheDocument()
  expect(within(nav()).getByRole('link', { name: /Chat de prueba/ })).toBeInTheDocument()
  expect(document.documentElement.lang).toBe('es')
  expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('es')

  const menu = await openConnectionMenu(user)
  expect(within(menu).getByRole('menuitem', { name: 'Desconectar' })).toBeInTheDocument()
  expect(within(menu).getByRole('group', { name: 'Tema' })).toBeInTheDocument()
  const language = within(menu).getByRole('group', { name: 'Idioma' })
  // The names stay in their own language; System is in the UI's.
  expect(within(language).getByRole('menuitemradio', { name: 'English' })).toHaveAttribute(
    'lang',
    'en',
  )
  expect(within(language).getByRole('menuitemradio', { name: 'Español' })).toBeChecked()
  await user.click(within(language).getByRole('menuitemradio', { name: 'Sistema' }))

  expect(within(nav()).getByRole('link', { name: 'Documents' })).toBeInTheDocument()
  expect(window.localStorage.getItem(LANGUAGE_KEY)).toBeNull()
})

test('System follows the browser while the page is open', () => {
  const browser = browserLanguages(['en-US'])
  renderApp('/settings', { connected: true })
  expect(within(nav()).getByRole('link', { name: 'Search' })).toBeInTheDocument()

  browser.set(['es-ES', 'en'])

  expect(within(nav()).getByRole('link', { name: 'Búsqueda' })).toBeInTheDocument()
  expect(document.documentElement.lang).toBe('es')
})

test('a stored choice wins over the browser', () => {
  window.localStorage.setItem(LANGUAGE_KEY, 'en')
  const browser = browserLanguages(['es'])
  renderApp('/settings', { connected: true })

  browser.set(['es-AR'])

  expect(within(nav()).getByRole('link', { name: 'Search' })).toBeInTheDocument()
})

test('a stored Spanish opens in Spanish, the 404 page included', async () => {
  renderApp('/no-such-page', { connected: true, language: 'es' })

  expect(await screen.findByRole('heading', { name: 'Página no encontrada' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Ir a documentos' })).toHaveAttribute(
    'href',
    '/documents',
  )
  expect(document.title).toBe('Página no encontrada · AYO Admin')
  expect(document.documentElement.lang).toBe('es')
})

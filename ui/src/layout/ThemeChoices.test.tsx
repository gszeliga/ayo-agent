import { act, within } from '@testing-library/react'

import { THEME_KEY } from '@/lib/theme'
import { openConnectionMenu, renderApp } from '@/test/render'

const isDark = () => document.documentElement.classList.contains('dark')

/** A controllable system preference: `setDark` fires the change event like the OS would. */
function systemTheme(dark: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const media = {
    matches: dark,
    addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    },
  }
  vi.spyOn(window, 'matchMedia').mockReturnValue(media as unknown as MediaQueryList)
  return {
    setDark: (next: boolean) => {
      media.matches = next
      act(() => {
        for (const listener of listeners) listener({ matches: next } as MediaQueryListEvent)
      })
    },
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  document.documentElement.classList.remove('dark')
})

test('the connection menu applies and stores the choice', async () => {
  systemTheme(false)
  const { user } = renderApp('/settings', { connected: true })
  expect(isDark()).toBe(false)

  let menu = await openConnectionMenu(user)
  await user.click(within(menu).getByRole('menuitemradio', { name: 'Dark' }))

  expect(isDark()).toBe(true)
  expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')

  menu = await openConnectionMenu(user)
  const theme = within(menu).getByRole('group', { name: 'Theme' })
  expect(within(theme).getByRole('menuitemradio', { name: 'Dark' })).toBeChecked()
  await user.click(within(theme).getByRole('menuitemradio', { name: 'System' }))
  expect(isDark()).toBe(false)
  expect(window.localStorage.getItem(THEME_KEY)).toBeNull()
})

test('system follows the OS while the page is open', () => {
  const system = systemTheme(false)
  renderApp('/settings', { connected: true })
  expect(isDark()).toBe(false)

  system.setDark(true)

  expect(isDark()).toBe(true)
})

test('a stored choice wins over the system', () => {
  window.localStorage.setItem(THEME_KEY, 'light')
  const system = systemTheme(true)
  renderApp('/settings', { connected: true })

  system.setDark(true)

  expect(isDark()).toBe(false)
})

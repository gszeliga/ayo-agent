import { act, screen } from '@testing-library/react'

import { THEME_KEY } from '@/lib/theme'
import { renderApp } from '@/test/render'

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

test('the toggle applies and stores the choice', async () => {
  systemTheme(false)
  const { user } = renderApp('/settings', { connected: true })
  expect(isDark()).toBe(false)

  await user.click(screen.getByRole('button', { name: 'Theme: system' }))
  await user.click(await screen.findByRole('menuitemradio', { name: 'Dark' }))

  expect(isDark()).toBe(true)
  expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
  expect(screen.getByRole('button', { name: 'Theme: dark' })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Theme: dark' }))
  await user.click(await screen.findByRole('menuitemradio', { name: 'System' }))
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

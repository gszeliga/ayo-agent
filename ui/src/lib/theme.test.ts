import BOOT from '../../public/theme-boot.js?raw'

import { readThemeChoice, resolveTheme, saveThemeChoice, THEME_KEY } from './theme'

/** Runs the shipped boot script as is, as the browser does before the app loads. */
function runBootScript(): void {
  // eslint-disable-next-line @typescript-eslint/no-implied-eval -- it is our own file, verbatim
  const script = new Function(BOOT) as () => void
  script()
}

function boot({ stored, systemDark }: { stored: string | null; systemDark: boolean }) {
  if (stored === null) window.localStorage.removeItem(THEME_KEY)
  else window.localStorage.setItem(THEME_KEY, stored)
  const matchMedia = vi
    .spyOn(window, 'matchMedia')
    .mockReturnValue({ matches: systemDark } as MediaQueryList)
  document.documentElement.classList.remove('dark')
  runBootScript()
  matchMedia.mockRestore()
  return document.documentElement.classList.contains('dark')
}

test.each([
  [null, false, false],
  [null, true, true],
  ['dark', false, true],
  ['light', true, false],
  ['nonsense', true, true],
])('the boot script: stored %j, system dark %j -> dark %j', (stored, systemDark, dark) => {
  expect(boot({ stored, systemDark })).toBe(dark)
})

test('the boot script survives blocked storage', () => {
  const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError')
  })
  try {
    expect(runBootScript).not.toThrow()
  } finally {
    getItem.mockRestore()
  }
})

test('the choice is stored, and system is the absence of one', () => {
  saveThemeChoice('dark')
  expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
  expect(readThemeChoice()).toBe('dark')
  saveThemeChoice('system')
  expect(window.localStorage.getItem(THEME_KEY)).toBeNull()
  expect(readThemeChoice()).toBe('system')
})

test('blocked storage reads as system', () => {
  const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError')
  })
  try {
    expect(readThemeChoice()).toBe('system')
    expect(() => {
      saveThemeChoice('dark')
    }).not.toThrow()
  } finally {
    getItem.mockRestore()
  }
})

test('resolving', () => {
  expect(resolveTheme('system', true)).toBe('dark')
  expect(resolveTheme('system', false)).toBe('light')
  expect(resolveTheme('light', true)).toBe('light')
})

export type ThemeChoice = 'light' | 'dark' | 'system'
export type Theme = 'light' | 'dark'

// The same key as public/theme-boot.js, which applies the choice before the first paint.
export const THEME_KEY = 'ayo.theme'
export const DARK_QUERY = '(prefers-color-scheme: dark)'

/** The stored choice; `system` when there is none or storage is blocked. */
export function readThemeChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  } catch {
    return 'system'
  }
}

/** Remembers the choice in this browser (a convenience: losing it means `system`). */
export function saveThemeChoice(choice: ThemeChoice): void {
  try {
    if (choice === 'system') window.localStorage.removeItem(THEME_KEY)
    else window.localStorage.setItem(THEME_KEY, choice)
  } catch {
    // Kept for this page only.
  }
}

export function resolveTheme(choice: ThemeChoice, systemDark: boolean): Theme {
  if (choice === 'system') return systemDark ? 'dark' : 'light'
  return choice
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

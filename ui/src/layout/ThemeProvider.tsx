import { useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  applyTheme,
  DARK_QUERY,
  readThemeChoice,
  resolveTheme,
  saveThemeChoice,
  type ThemeChoice,
} from '@/lib/theme'

import { ThemeContext } from './themeContext'

/** Light, dark, or the system's; `system` follows the OS while the page is open. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>(readThemeChoice)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(DARK_QUERY).matches)
  const theme = resolveTheme(choice, systemDark)

  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY)
    const onChange = (event: MediaQueryListEvent) => {
      setSystemDark(event.matches)
    }
    media.addEventListener('change', onChange)
    return () => {
      media.removeEventListener('change', onChange)
    }
  }, [])

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const value = useMemo(
    () => ({
      choice,
      theme,
      setChoice: (next: ThemeChoice) => {
        saveThemeChoice(next)
        setChoice(next)
      },
    }),
    [choice, theme],
  )
  return <ThemeContext value={value}>{children}</ThemeContext>
}

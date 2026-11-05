import { createContext, useContext } from 'react'

import type { Theme, ThemeChoice } from '@/lib/theme'

export interface ThemeState {
  choice: ThemeChoice
  /** What is shown: the choice, or the system's theme for `system`. */
  theme: Theme
  setChoice: (choice: ThemeChoice) => void
}

export const ThemeContext = createContext<ThemeState | null>(null)

export function useTheme(): ThemeState {
  const state = useContext(ThemeContext)
  if (state === null) throw new Error('useTheme needs a <ThemeProvider>')
  return state
}

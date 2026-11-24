import { createContext, useContext } from 'react'

import type { Language, LanguageChoice } from '@/lib/language'

export interface LanguageState {
  choice: LanguageChoice
  /** What is shown: the choice, or the browser's language for `system`. */
  language: Language
  setChoice: (choice: LanguageChoice) => void
}

export const LanguageContext = createContext<LanguageState | null>(null)

export function useLanguage(): LanguageState {
  const state = useContext(LanguageContext)
  if (state === null) throw new Error('useLanguage needs a <LanguageProvider>')
  return state
}

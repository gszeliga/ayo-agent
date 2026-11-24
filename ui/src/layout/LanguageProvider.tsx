import { useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'

import { i18n } from '@/i18n'
import {
  readLanguageChoice,
  resolveLanguage,
  saveLanguageChoice,
  systemLanguage,
  type LanguageChoice,
} from '@/lib/language'

import { LanguageContext } from './languageContext'

/** English, Spanish, or the browser's; `system` follows the browser while the page is open. */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<LanguageChoice>(readLanguageChoice)
  const [system, setSystem] = useState(() => systemLanguage())
  const language = resolveLanguage(choice, system)

  useEffect(() => {
    const onChange = () => {
      setSystem(systemLanguage())
    }
    window.addEventListener('languagechange', onChange)
    return () => {
      window.removeEventListener('languagechange', onChange)
    }
  }, [])

  // Before the paint: a switch never shows a frame in the old language. i18next starts in
  // this language already (`@/i18n`), so the first render needs no switch.
  useLayoutEffect(() => {
    if (i18n.language !== language) void i18n.changeLanguage(language)
    document.documentElement.lang = language
  }, [language])

  const value = useMemo(
    () => ({
      choice,
      language,
      setChoice: (next: LanguageChoice) => {
        saveLanguageChoice(next)
        setChoice(next)
      },
    }),
    [choice, language],
  )
  return <LanguageContext value={value}>{children}</LanguageContext>
}

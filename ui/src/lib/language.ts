export type Language = 'en' | 'es'
export type LanguageChoice = Language | 'system'

export const LANGUAGES: readonly Language[] = ['en', 'es']

/** Each language's name in that language: the picker shows them the same in any UI language. */
export const LANGUAGE_NAMES: Record<Language, string> = { en: 'English', es: 'Español' }

/** The `Intl` locale for dates and numbers: "5 Oct 2026" and "5 oct 2026". */
export const INTL_LOCALE: Record<Language, string> = { en: 'en-GB', es: 'es-ES' }

export const LANGUAGE_KEY = 'ayo.lang'

function isLanguage(value: unknown): value is Language {
  return LANGUAGES.includes(value as Language)
}

/** The stored choice; `system` when there is none or storage is blocked. */
export function readLanguageChoice(): LanguageChoice {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_KEY)
    return isLanguage(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

/** Remembers the choice in this browser (a convenience: losing it means `system`). */
export function saveLanguageChoice(choice: LanguageChoice): void {
  try {
    if (choice === 'system') window.localStorage.removeItem(LANGUAGE_KEY)
    else window.localStorage.setItem(LANGUAGE_KEY, choice)
  } catch {
    // Kept for this page only.
  }
}

/** The browser's first preferred language that the UI has ("es-AR" is Spanish), else English. */
export function systemLanguage(preferred: readonly string[] = navigator.languages): Language {
  for (const tag of preferred) {
    const base = tag.toLowerCase().split('-')[0]
    if (isLanguage(base)) return base
  }
  return 'en'
}

export function resolveLanguage(choice: LanguageChoice, system: Language): Language {
  return choice === 'system' ? system : choice
}

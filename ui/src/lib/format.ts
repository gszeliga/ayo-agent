import { i18n } from '@/i18n'

import { INTL_LOCALE, type Language } from './language'

const MINUTE = 60
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** One `Intl` formatter per language and kind, made the first time it is needed. */
function cachedPerLanguage<T>(make: (locale: string) => T): (language: Language) => T {
  const cache = new Map<Language, T>()
  return (language) => {
    let made = cache.get(language)
    if (made === undefined) {
      made = make(INTL_LOCALE[language])
      cache.set(language, made)
    }
    return made
  }
}

const dateFormat = cachedPerLanguage(
  (locale) =>
    new Intl.DateTimeFormat(locale, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    }),
)

// One decimal, no grouping: "1023.9 KB" as before, "4,2 KB" in Spanish.
const oneDecimal = cachedPerLanguage(
  (locale) =>
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
      useGrouping: false,
    }),
)

const words = (language: Language) => i18n.getFixedT(language, 'common')

/**
 * "just now", "5 min ago", "3 h ago", "2 d ago", then a date ("5 Oct 2026") after 30 days;
 * "ahora mismo", "hace 5 min", ..., "5 oct 2026" in Spanish.
 */
export function relativeTime(
  iso: string,
  language: Language = 'en',
  now: number = Date.now(),
): string {
  const t = words(language)
  const seconds = Math.floor((now - Date.parse(iso)) / 1000)
  if (seconds < MINUTE) return t('time.justNow') // also a timestamp slightly ahead of this clock
  if (seconds < HOUR) return t('time.minutesAgo', { n: Math.floor(seconds / MINUTE) })
  if (seconds < DAY) return t('time.hoursAgo', { n: Math.floor(seconds / HOUR) })
  if (seconds < 30 * DAY) return t('time.daysAgo', { n: Math.floor(seconds / DAY) })
  return dateFormat(language).format(new Date(iso))
}

/** The exact time, for a tooltip, in every language: "2026-11-05 10:14 UTC". */
export function formatUtc(iso: string): string {
  const date = new Date(iso)
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

/** 1024-based, one decimal: "512 B", "4.2 KB", "1.5 MB" ("4,2 KB" in Spanish). */
export function formatBytes(bytes: number, language: Language = 'en'): string {
  const t = words(language)
  if (bytes < 1024) return t('size.bytes', { n: bytes })
  const decimal = oneDecimal(language)
  if (bytes < 1024 * 1024) return t('size.kilobytes', { n: decimal.format(bytes / 1024) })
  return t('size.megabytes', { n: decimal.format(bytes / (1024 * 1024)) })
}

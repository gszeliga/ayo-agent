import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

// A rule rather than a measurement: predictable, and testable without a layout engine.
const CLAMP_LINES = 3
const CLAMP_CHARS = 260

/** A chunk shown clamped to three lines, with "Show more". */
export function isLong(text: string): boolean {
  return text.split('\n').length > CLAMP_LINES || text.length > CLAMP_CHARS
}

/** "All tenants", one or two names, or how many. */
export function tenantsSummary(tenants: string[], language: Language = 'en'): string {
  const t = i18n.getFixedT(language, 'search')
  if (tenants.length === 0) return t('tenants.all')
  if (tenants.length <= 2) return tenants.join(' + ')
  return t('tenants.some', { count: tenants.length })
}

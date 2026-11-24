import { i18n } from '@/i18n'
import { formatDecimal } from '@/lib/format'
import type { Language } from '@/lib/language'

const words = (language: Language) => i18n.getFixedT(language, 'chat')

/**
 * A cost in US dollars: two decimals from a cent up, four below, "<$0.0001" for less;
 * "0,02 $", "<0,0001 $" in Spanish.
 */
export function formatCost(cost: number, language: Language = 'en'): string {
  const t = words(language)
  if (cost === 0) return t('format.cost', { n: formatDecimal(0, language, { min: 2 }) })
  if (cost < 0.0001) {
    return t('format.costBelow', { n: formatDecimal(0.0001, language, { min: 4 }) })
  }
  return t('format.cost', { n: formatDecimal(cost, language, { min: cost < 0.01 ? 4 : 2 }) })
}

/** "850 tokens", "12.3k tokens", "1.2M tokens" ("12,3k tokens" in Spanish). */
export function formatTokens(tokens: number, language: Language = 'en'): string {
  const t = words(language)
  if (tokens < 1000) return t('format.tokens', { count: tokens })
  if (tokens < 1_000_000) {
    return t('format.tokensThousands', { n: trim(tokens / 1000, language) })
  }
  return t('format.tokensMillions', { n: trim(tokens / 1_000_000, language) })
}

/** One decimal at most: "12.3", "1" (not "1.0"). */
function trim(value: number, language: Language): string {
  return formatDecimal(value, language, { min: 0, max: 1 })
}

/** "850 ms", "4.5 s", "12 s" ("4,5 s" in Spanish). */
export function formatDuration(ms: number, language: Language = 'en'): string {
  const t = words(language)
  if (ms < 1000) return t('format.milliseconds', { n: String(Math.round(ms)) })
  const seconds = ms / 1000
  return t('format.seconds', {
    n: seconds < 10 ? formatDecimal(seconds, language, { min: 1 }) : String(Math.round(seconds)),
  })
}

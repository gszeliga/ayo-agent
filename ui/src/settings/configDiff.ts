/**
 * What changed between a document's stored config and the current one, in words. The
 * config strings are the backend's descriptors (`signatures.chunker_descriptor` and
 * `embedder_descriptor`); configDiff.test.ts pins their format against docs/openapi.json.
 *   chunker:  md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1
 *   embedder: voyage-4/document/1024
 * The part names are in the `document` catalog (`configPart.*`); an unknown part shows as is.
 */
import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

type Parts = Map<string, string>

const PARTS = [
  'version',
  'size',
  'overlap',
  'min',
  'merge',
  'breadcrumb',
  'model',
  'input',
  'dimensions',
] as const
type KnownPart = (typeof PARTS)[number]

function partLabel(key: string, language: Language): string {
  if (!(PARTS as readonly string[]).includes(key)) return key
  return i18n.getFixedT(language, 'document')(`configPart.${key as KnownPart}`)
}

export function parseChunkerConfig(config: string): Parts | null {
  const [version, ...rest] = config.split('/')
  if (!version?.includes('@') || rest.length === 0) return null
  const parts: Parts = new Map([['version', version]])
  for (const part of rest) {
    const at = part.indexOf('=')
    if (at <= 0) return null
    parts.set(part.slice(0, at), part.slice(at + 1))
  }
  return parts
}

export function parseEmbedderConfig(config: string): Parts | null {
  const [model, input, dimensions, ...extra] = config.split('/')
  if (!model || !input || !dimensions || extra.length > 0) return null
  return new Map([
    ['model', model],
    ['input', input],
    ['dimensions', dimensions],
  ])
}

/**
 * The changes, e.g. ["size 800 → 1000"]; [] when equal; null when either string cannot be
 * read (the caller then says only that it differs).
 */
function diff(
  stored: string,
  current: string,
  parse: (config: string) => Parts | null,
  language: Language,
): string[] | null {
  if (stored === current) return []
  const before = parse(stored)
  const after = parse(current)
  if (!before || !after) return null
  const keys = [...new Set([...before.keys(), ...after.keys()])]
  return keys
    .filter((key) => before.get(key) !== after.get(key))
    .map(
      (key) => `${partLabel(key, language)} ${before.get(key) ?? '—'} → ${after.get(key) ?? '—'}`,
    )
}

export const chunkerDiff = (stored: string, current: string, language: Language = 'en') =>
  diff(stored, current, parseChunkerConfig, language)

export const embedderDiff = (stored: string, current: string, language: Language = 'en') =>
  diff(stored, current, parseEmbedderConfig, language)

/** The note under a config in the facts panel, or null when nothing differs. */
export function differsNote(changes: string[] | null, language: Language = 'en'): string | null {
  const t = i18n.getFixedT(language, 'document')
  if (changes === null) return t('differs')
  return changes.length === 0 ? null : t('nowDiffers', { changes: changes.join(', ') })
}

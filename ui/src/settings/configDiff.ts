/**
 * What changed between a document's stored config and the current one, in words. The
 * config strings are the backend's descriptors (`signatures.chunker_descriptor` and
 * `embedder_descriptor`); configDiff.test.ts pins their format against docs/openapi.json.
 *   chunker:  md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1
 *   embedder: voyage-4/document/1024
 */
type Parts = Map<string, string>

const CHUNKER_LABELS: Record<string, string> = {
  version: 'version',
  size: 'size',
  overlap: 'overlap',
  min: 'min size',
  merge: 'small-chunk policy',
  breadcrumb: 'heading breadcrumb',
}

const EMBEDDER_LABELS: Record<string, string> = {
  model: 'model',
  input: 'input type',
  dimensions: 'dimensions',
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
  labels: Record<string, string>,
): string[] | null {
  if (stored === current) return []
  const before = parse(stored)
  const after = parse(current)
  if (!before || !after) return null
  const keys = [...new Set([...before.keys(), ...after.keys()])]
  return keys
    .filter((key) => before.get(key) !== after.get(key))
    .map((key) => `${labels[key] ?? key} ${before.get(key) ?? '—'} → ${after.get(key) ?? '—'}`)
}

export const chunkerDiff = (stored: string, current: string) =>
  diff(stored, current, parseChunkerConfig, CHUNKER_LABELS)

export const embedderDiff = (stored: string, current: string) =>
  diff(stored, current, parseEmbedderConfig, EMBEDDER_LABELS)

/** The note under a config in the facts panel, or null when nothing differs. */
export function differsNote(changes: string[] | null): string | null {
  if (changes === null) return 'Differs from the current settings'
  return changes.length === 0 ? null : `Now differs: ${changes.join(', ')}`
}

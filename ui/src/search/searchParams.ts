import type { components } from '@/api/schema'
import { TENANT_PATTERN } from '@/documents/listParams'

export type SearchRequest = components['schemas']['SearchRequest']

// The API's own limits (docs/openapi.json; searchParams.test.ts checks they still match), so
// neither a hand-edited URL nor the form turns into a 422.
export const QUERY_MAX_CHARS = 2000
export const MAX_TENANTS = 50
export const MAX_TOP_K = 50

/**
 * Where and how to search: what the URL holds. **Never the question**: a question in the URL
 * would reach the browser's history and the proxy's access log, and the API treats queries
 * as sensitive as documents.
 */
export interface SearchOptions {
  /** Empty: every tenant. Sorted, no repeats. */
  tenants: string[]
  topK: number
  minSimilarity: number | null
  includeOutdated: boolean
}

export const DEFAULT_OPTIONS: SearchOptions = {
  tenants: [],
  topK: 5,
  minSimilarity: null,
  includeOutdated: false,
}

/** 1 to 50, a whole number. */
export function parseTopK(text: string): number | null {
  const value = text.trim()
  if (!/^[0-9]{1,2}$/.test(value)) return null
  const k = Number(value)
  return k >= 1 && k <= MAX_TOP_K ? k : null
}

/** 0 to 1, at most 4 decimals (the similarity's own precision); a decimal comma is fine. */
export function parseMinSimilarity(text: string): number | null {
  const value = text.trim().replace(',', '.')
  if (!/^(0|1)?(\.[0-9]{1,4})?$/.test(value) || value === '' || value === '.') return null
  const min = Number(value)
  return min >= 0 && min <= 1 ? min : null
}

/** The options from the URL; invalid values fall back to their defaults. */
export function parseSearchOptions(search: URLSearchParams): SearchOptions {
  const tenants = [...new Set(search.getAll('tenant').filter((t) => TENANT_PATTERN.test(t)))]
  const k = search.get('k')
  const min = search.get('min')
  return {
    tenants: tenants.length <= MAX_TENANTS ? tenants.sort() : DEFAULT_OPTIONS.tenants,
    topK: (k !== null ? parseTopK(k) : null) ?? DEFAULT_OPTIONS.topK,
    minSimilarity: min !== null ? parseMinSimilarity(min) : DEFAULT_OPTIONS.minSimilarity,
    includeOutdated: search.get('outdated') === '1',
  }
}

/** The URL for the options: defaults left out, keys in a fixed order. */
export function toSearchParams(options: SearchOptions): URLSearchParams {
  const search = new URLSearchParams()
  for (const tenant of options.tenants) search.append('tenant', tenant)
  if (options.topK !== DEFAULT_OPTIONS.topK) search.set('k', String(options.topK))
  if (options.minSimilarity !== null) search.set('min', String(options.minSimilarity))
  if (options.includeOutdated) search.set('outdated', '1')
  return search
}

/** Characters as the API counts them (code points, not UTF-16 units). */
export function charCount(text: string): number {
  return Array.from(text).length
}

/** The request for a question. `debug` is always on: it costs nothing and feeds the timings. */
export function toRequest(question: string, options: SearchOptions): SearchRequest {
  return {
    query: question.trim(),
    ...(options.tenants.length > 0 ? { tenants: options.tenants } : {}),
    top_k: options.topK,
    ...(options.minSimilarity !== null ? { min_similarity: options.minSimilarity } : {}),
    include_outdated: options.includeOutdated,
    debug: true,
  }
}

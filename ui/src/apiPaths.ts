/**
 * The API's paths on a shared origin: the Vite proxy in development and Caddy in
 * production (plans/ui-progress.md decision 5) send these to the API and serve the UI for
 * everything else. No DOM or Node here: `vite.config.ts` imports it too.
 */

/** The API's own pages, besides the paths in the contract. */
export const API_DOC_PATHS = ['/docs', '/redoc', '/openapi.json']

/** The first segment of every contract path, plus the API's own pages. */
export function apiPrefixes(contractPaths: Iterable<string>): string[] {
  const fromContract = [...contractPaths].map((path) => `/${path.split('/')[1] ?? ''}`)
  return [...new Set([...fromContract, ...API_DOC_PATHS])]
}

/** Whether a path (query string allowed) is the prefix itself or below it. */
export function isUnderPrefix(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}?`)
}

/**
 * The prefix as a Vite proxy key: a key starting with `^` is a regular expression, tested
 * on the path with its query string. Same rule as `isUnderPrefix`, so `/admin` never
 * catches `/administration`.
 */
export function proxyPattern(prefix: string): string {
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return `^${escaped}(?:[/?]|$)`
}

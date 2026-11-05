/**
 * The API base URL: `scheme://host[:port]`, no path. Defaults to `VITE_API_BASE_URL` when
 * set at build time, else the page's own origin (the UI and the API share an origin in
 * production, plans/ui-progress.md decision 5).
 */
export function defaultBaseUrl(
  configured: string | undefined = import.meta.env.VITE_API_BASE_URL,
  origin: string = window.location.origin,
): string {
  const fromBuild = configured?.trim() ? normalizeBaseUrl(configured) : null
  return fromBuild ?? origin
}

/** The URL as `scheme://host[:port]`, or null if it is not an http(s) URL without a path. */
export function normalizeBaseUrl(value: string): string | null {
  let url: URL
  try {
    url = new URL(value.trim())
  } catch {
    return null
  }
  const pathless = url.pathname === '/' && !url.search && !url.hash
  if (!['http:', 'https:'].includes(url.protocol) || !pathless || url.username || url.password) {
    return null
  }
  return url.origin
}

export interface Connection {
  baseUrl: string
  apiKey: string
}

const KEY = 'ayo.connection'

function isConnection(value: unknown): value is Connection {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.baseUrl === 'string' && typeof candidate.apiKey === 'string'
}

/**
 * The connection lives in `sessionStorage`: this tab only, gone when it closes. Storage can
 * be blocked (private modes, policies); then it lasts until the page reloads.
 */
export function loadConnection(
  storage: Storage | undefined = safeSessionStorage(),
): Connection | null {
  try {
    const raw = storage?.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    return isConnection(parsed) ? { baseUrl: parsed.baseUrl, apiKey: parsed.apiKey } : null
  } catch {
    return null
  }
}

export function saveConnection(
  connection: Connection,
  storage: Storage | undefined = safeSessionStorage(),
): void {
  try {
    storage?.setItem(KEY, JSON.stringify(connection))
  } catch {
    // Kept in memory only.
  }
}

export function clearConnection(storage: Storage | undefined = safeSessionStorage()): void {
  try {
    storage?.removeItem(KEY)
  } catch {
    // Nothing stored.
  }
}

function safeSessionStorage(): Storage | undefined {
  try {
    return window.sessionStorage
  } catch {
    return undefined
  }
}

import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

const PROBE_TIMEOUT_MS = 3000

/**
 * Whether anything answers at `baseUrl`, CORS aside. A browser reports a CORS refusal
 * exactly like a network failure; a `no-cors` request is exempt from CORS (its response
 * is opaque, but it only succeeds if the server answered), so after a failed call it tells
 * the two apart. Uses the public `/health`, which needs no key.
 */
export async function isServerReachable(
  baseUrl: string,
  fetchFn: typeof globalThis.fetch = (...args) => globalThis.fetch(...args),
): Promise<boolean> {
  try {
    await fetchFn(`${baseUrl}/health`, {
      mode: 'no-cors',
      cache: 'no-store',
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    })
    return true
  } catch {
    return false
  }
}

/** Why a call failed without an answer: CORS when the server answers, else unreachable. */
export function unreachableMessage(
  baseUrl: string,
  reachable: boolean,
  origin: string,
  language: Language = 'en',
): string {
  const t = i18n.getFixedT(language, 'common')
  return reachable
    ? t('errors.corsRefused', { baseUrl, origin })
    : t('errors.unreachable', { baseUrl })
}

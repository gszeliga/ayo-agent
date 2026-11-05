/** `next` only if it is a path inside this app; never another site (`//x`, `https://x`). */
export function safeNext(next: string | null, fallback = '/documents'): string {
  if (!next?.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return fallback
  if (next === '/connect' || next.startsWith('/connect?')) return fallback
  return next
}

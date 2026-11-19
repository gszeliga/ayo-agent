/**
 * Every path the UI routes. In production the UI and the API share an origin and the proxy
 * sends the API's paths to it, so none of these may start with one (paths.test.ts checks).
 */
export const ROUTES = {
  connect: '/connect',
  documents: '/documents',
  document: '/documents/:docId',
  settings: '/settings',
  search: '/search',
  chat: '/chat',
  chatNew: '/chat/new',
  chatCase: '/chat/:caseId',
} as const

/** The test chat on one case. */
export function chatCasePath(caseId: string): string {
  return `${ROUTES.chat}/${encodeURIComponent(caseId)}`
}

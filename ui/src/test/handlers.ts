import { http, HttpResponse, type RequestHandler } from 'msw'

import { makeHealth, makeSettings } from './fixtures/services'

/**
 * What every page asks for besides its own data: the header's service status and the
 * current settings. A healthy API by default; a test overrides them with `server.use(...)`.
 * Matched on the path, whatever the API's base URL.
 */
export const handlers: RequestHandler[] = [
  http.get('*/admin/health', () => HttpResponse.json(makeHealth())),
  http.get('*/admin/settings', () => HttpResponse.json(makeSettings())),
]

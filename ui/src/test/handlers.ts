import type { RequestHandler } from 'msw'

/** Default handlers for every test; a test adds its own with `server.use(...)`. */
export const handlers: RequestHandler[] = []

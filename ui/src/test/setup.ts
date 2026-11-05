import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'

import { server } from './server'

// A request no handler answers fails the test: no test can reach a real API.
beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' })
})
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => {
  server.close()
})

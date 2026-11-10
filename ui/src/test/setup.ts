import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'

import { server } from './server'

// jsdom has no matchMedia; the toaster's system theme asks for it. Tests run light.
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}

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

// jsdom has no pointer capture; the toaster's swipe handling calls it when a toast's
// button is clicked. No-ops are enough: tests don't swipe.
for (const method of ['setPointerCapture', 'releasePointerCapture'] as const) {
  if (typeof Element.prototype[method] !== 'function') Element.prototype[method] = () => undefined
}
// jsdom has no scrollIntoView; a chunk opened from a search result scrolls to itself.
if (typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = () => undefined
}
if (typeof Element.prototype.hasPointerCapture !== 'function') {
  Element.prototype.hasPointerCapture = () => false
}

// Each test starts disconnected and with the banner showing.
beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
})

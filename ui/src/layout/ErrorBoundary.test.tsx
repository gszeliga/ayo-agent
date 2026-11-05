import { render, screen } from '@testing-library/react'

import { isChunkLoadError } from '@/lib/chunkError'

import { ErrorBoundary } from './ErrorBoundary'

function Boom({ error }: { error: Error }): never {
  throw error
}

beforeEach(() => {
  // React and the boundary log the caught error; keep the test output clean.
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})
afterEach(() => {
  vi.restoreAllMocks()
})

test('a crash shows a way out instead of a blank page', () => {
  render(
    <ErrorBoundary resetKey="/documents">
      <Boom error={new TypeError("Cannot read properties of undefined (reading 'items')")} />
    </ErrorBoundary>,
  )

  expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Back to documents' })).toHaveAttribute(
    'href',
    '/documents',
  )
})

test('a lazy chunk that is gone asks for a reload', () => {
  render(
    <ErrorBoundary resetKey="/settings">
      <Boom
        error={
          new TypeError('Failed to fetch dynamically imported module: /assets/SettingsPage-x.js')
        }
      />
    </ErrorBoundary>,
  )

  expect(
    screen.getByRole('heading', { name: 'A new version of this page is available' }),
  ).toBeInTheDocument()
})

test('another path clears the error', () => {
  const { rerender } = render(
    <ErrorBoundary resetKey="/a">
      <Boom error={new Error('x')} />
    </ErrorBoundary>,
  )

  rerender(
    <ErrorBoundary resetKey="/b">
      <p>fine</p>
    </ErrorBoundary>,
  )

  expect(screen.getByText('fine')).toBeInTheDocument()
})

test.each([
  ['Failed to fetch dynamically imported module: x', true], // Chrome
  ['error loading dynamically imported module: x', true], // Firefox
  ['Importing a module script failed.', true], // Safari
  ['Cannot read properties of undefined', false],
])('%j is a chunk error: %j', (message, expected) => {
  expect(isChunkLoadError(new TypeError(message))).toBe(expected)
})

import openapi from '../../docs/openapi.json'

import { ROUTES } from './paths'

// The API's own pages, besides the paths in the contract.
const API_DOC_PATHS = ['/docs', '/redoc', '/openapi.json']

/** First segment of every API path: on a shared origin the proxy sends these to the API. */
function apiPrefixes(): string[] {
  const fromContract = Object.keys(openapi.paths).map((path) => `/${path.split('/')[1] ?? ''}`)
  return [...new Set([...fromContract, ...API_DOC_PATHS])]
}

function clashes(route: string, prefix: string): boolean {
  return route === prefix || route.startsWith(`${prefix}/`) || route.startsWith(`${prefix}?`)
}

test('the API prefixes are read from the contract', () => {
  expect(apiPrefixes()).toEqual(expect.arrayContaining(['/admin', '/health', '/docs']))
})

test('no UI route starts with an API path', () => {
  const clashing = Object.values(ROUTES).flatMap((route) =>
    apiPrefixes()
      .filter((prefix) => clashes(route, prefix))
      .map((prefix) => `${route} (API ${prefix})`),
  )

  expect(clashing).toEqual([])
})

test('the check would catch a clash', () => {
  expect(clashes('/admin/x', '/admin')).toBe(true)
  expect(clashes('/administration', '/admin')).toBe(false)
})

import openapi from '../../docs/openapi.json'

import { apiPrefixes, isUnderPrefix } from './apiPaths'
import { ROUTES } from './paths'

test('no UI route starts with an API path', () => {
  const prefixes = apiPrefixes(Object.keys(openapi.paths))
  const clashing = Object.values(ROUTES).flatMap((route) =>
    prefixes
      .filter((prefix) => isUnderPrefix(route, prefix))
      .map((prefix) => `${route} (API ${prefix})`),
  )

  expect(clashing).toEqual([])
})

test('the check would catch a clash', () => {
  expect(isUnderPrefix('/admin/x', '/admin')).toBe(true)
  expect(isUnderPrefix('/administration', '/admin')).toBe(false)
})

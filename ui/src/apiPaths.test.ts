import openapi from '../../docs/openapi.json'

import { apiPrefixes, isUnderPrefix, proxyPattern } from './apiPaths'
import { ROUTES } from './paths'

const contractPaths = Object.keys(openapi.paths)
const patterns = apiPrefixes(contractPaths).map((prefix) => new RegExp(proxyPattern(prefix)))

function proxied(path: string): boolean {
  return patterns.some((pattern) => pattern.test(path))
}

test('the prefixes are read from the contract', () => {
  expect(apiPrefixes(contractPaths)).toEqual(
    expect.arrayContaining(['/admin', '/copilot', '/health', '/docs', '/redoc', '/openapi.json']),
  )
})

test('the proxy sends every contract path to the API', () => {
  // Path parameters filled in, as the browser sends them.
  const concrete = contractPaths.map((path) => path.replace(/\{[^}]+\}/g, 'x'))

  expect(concrete.filter((path) => !proxied(path))).toEqual([])
  expect(proxied('/admin/documents?tenant=acme&page=2')).toBe(true)
  expect(proxied('/openapi.json')).toBe(true)
})

test('the proxy leaves every UI route to the UI', () => {
  const routes = Object.values(ROUTES)

  expect(routes.filter(proxied)).toEqual([])
  expect(proxied('/')).toBe(false)
  expect(proxied('/administration')).toBe(false)
  expect(proxied('/openapiXjson')).toBe(false)
})

test('a proxy pattern follows the same rule as isUnderPrefix', () => {
  const samples = ['/admin', '/admin/x', '/admin?x=1', '/administration', '/adm', '/x/admin']
  const pattern = new RegExp(proxyPattern('/admin'))

  for (const sample of samples) {
    expect(pattern.test(sample)).toBe(isUnderPrefix(sample, '/admin'))
  }
})

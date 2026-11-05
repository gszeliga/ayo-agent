import { defaultBaseUrl, normalizeBaseUrl } from './baseUrl'

test.each([
  ['http://127.0.0.1:8000', 'http://127.0.0.1:8000'],
  ['https://API.example.com/', 'https://api.example.com'],
  ['  https://api.example.com:8443  ', 'https://api.example.com:8443'],
])('%j is normalized to %j', (input, expected) => {
  expect(normalizeBaseUrl(input)).toBe(expected)
})

test.each([
  '',
  'api.example.com',
  'ftp://host',
  'https://host/admin',
  'https://host?x=1',
  'https://u:p@host',
  'nonsense',
])('%j is refused', (input) => {
  expect(normalizeBaseUrl(input)).toBeNull()
})

test('the build-time setting wins over the page origin', () => {
  expect(defaultBaseUrl('http://127.0.0.1:8000/', 'https://admin.example.com')).toBe(
    'http://127.0.0.1:8000',
  )
})

test.each([undefined, '', '  ', 'not a url'])(
  'without a usable setting (%j) the page origin is the default',
  (configured) => {
    expect(defaultBaseUrl(configured, 'https://admin.example.com')).toBe(
      'https://admin.example.com',
    )
  },
)

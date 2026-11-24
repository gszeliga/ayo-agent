import {
  LANGUAGE_KEY,
  readLanguageChoice,
  resolveLanguage,
  saveLanguageChoice,
  systemLanguage,
} from './language'

afterEach(() => {
  vi.restoreAllMocks()
})

test('the choice round-trips; system is the absence of one', () => {
  expect(readLanguageChoice()).toBe('system')

  saveLanguageChoice('es')
  expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('es')
  expect(readLanguageChoice()).toBe('es')

  saveLanguageChoice('system')
  expect(window.localStorage.getItem(LANGUAGE_KEY)).toBeNull()
  expect(readLanguageChoice()).toBe('system')
})

test('an unknown stored value reads as system', () => {
  window.localStorage.setItem(LANGUAGE_KEY, 'fr')
  expect(readLanguageChoice()).toBe('system')
})

test('blocked storage means system, and saving does not throw', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError')
  })

  expect(readLanguageChoice()).toBe('system')
  expect(() => {
    saveLanguageChoice('es')
  }).not.toThrow()
})

test.each([
  [['es-AR'], 'es'],
  [['es'], 'es'],
  [['ES-es'], 'es'],
  [['fr', 'es-MX'], 'es'], // the first language the UI has
  [['en-US', 'es'], 'en'],
  [['fr'], 'en'],
  [[], 'en'],
])('the browser preferring %j gives %j', (preferred, expected) => {
  expect(systemLanguage(preferred)).toBe(expected)
})

test('a choice wins over the system', () => {
  expect(resolveLanguage('en', 'es')).toBe('en')
  expect(resolveLanguage('system', 'es')).toBe('es')
})

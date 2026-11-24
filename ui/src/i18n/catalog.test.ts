import { LANGUAGES } from '@/lib/language'

import { NAMESPACES, resources } from './resources'

const PLURAL = /_(zero|one|two|few|many|other)$/

/** Every string in a catalog by its dotted key. */
function flatten(tree: object, prefix = ''): Map<string, string> {
  const flat = new Map<string, string>()
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') flat.set(path, value)
    else for (const [k, v] of flatten(value as object, path)) flat.set(k, v)
  }
  return flat
}

const placeholders = (text: string) =>
  [...text.matchAll(/\{\{\s*([\w.]+)[^}]*\}\}/g)].map((m) => m[1]).sort()

// `<Trans>` components (`<phrase/>`, `<b>…</b>`): a missing or renamed one loses its element.
const tags = (text: string) => [...text.matchAll(/<\/?(\w+)\s*\/?>/g)].map((m) => m[0]).sort()

const others = LANGUAGES.filter((language) => language !== 'en')

describe.each(NAMESPACES)('the %s namespace', (namespace) => {
  const english = flatten(resources.en[namespace])

  test.each(others)('%s has the same keys as English', (language) => {
    const translated = flatten(resources[language][namespace])
    expect([...translated.keys()].sort()).toEqual([...english.keys()].sort())
  })

  test.each(others)('%s has the same placeholders in every string', (language) => {
    const translated = flatten(resources[language][namespace])
    for (const [key, text] of english) {
      expect({ key, placeholders: placeholders(translated.get(key) ?? '') }).toEqual({
        key,
        placeholders: placeholders(text),
      })
    }
  })

  test.each(others)('%s has the same <Trans> tags in every string', (language) => {
    const translated = flatten(resources[language][namespace])
    for (const [key, text] of english) {
      expect({ key, tags: tags(translated.get(key) ?? '') }).toEqual({ key, tags: tags(text) })
    }
  })

  test.each(LANGUAGES)('%s has no empty string', (language) => {
    for (const [key, text] of flatten(resources[language][namespace])) {
      expect({ key, empty: text.trim() === '' }).toEqual({ key, empty: false })
    }
  })

  // i18next falls back to `_other` for a form a catalog lacks (Spanish `_many`), so one and
  // other are enough; the same keys in every language are checked above.
  test('every plural has an `_other` form', () => {
    const keys = [...english.keys()]
    for (const key of keys.filter((k) => PLURAL.test(k))) {
      expect(keys).toContain(key.replace(PLURAL, '_other'))
    }
  })
})

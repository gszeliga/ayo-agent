import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { readLanguageChoice, resolveLanguage, systemLanguage } from '@/lib/language'

import { NAMESPACES, resources } from './resources'

// Initialised at import, synchronously (bundled resources, no backend): the first render
// is already in the stored or the system's language. `LanguageProvider` switches it later.
void i18n.use(initReactI18next).init({
  resources,
  lng: resolveLanguage(readLanguageChoice(), systemLanguage()),
  fallbackLng: 'en',
  supportedLngs: ['en', 'es'],
  ns: NAMESPACES,
  defaultNS: 'common',
  initAsync: false,
  // React escapes what it renders.
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
})

export { i18n }

import 'i18next'

import type { Catalog } from './catalog'

// Typed keys: `t('typo')` fails `tsc`.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common'
    resources: Catalog
  }
}

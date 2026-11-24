import type { en } from './locales/en'

/**
 * A language's catalogs: the English shape, one namespace per area. A missing or extra key
 * in another language fails `tsc`.
 */
export type Catalog = typeof en

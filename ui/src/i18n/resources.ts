import type { Language } from '@/lib/language'

import type { Catalog } from './catalog'
import { en } from './locales/en'
import { es } from './locales/es'

/** Every language's catalogs, bundled: nothing is fetched, so nothing shows untranslated. */
export const resources: Record<Language, Catalog> = { en, es }

export const NAMESPACES = Object.keys(en) as (keyof Catalog)[]

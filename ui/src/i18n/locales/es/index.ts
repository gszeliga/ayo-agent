import type { Catalog } from '../../catalog'

import { common } from './common'
import { connect } from './connect'
import { document } from './document'
import { documents } from './documents'
import { settings } from './settings'
import { upload } from './upload'

export const es: Catalog = { common, connect, document, documents, settings, upload }

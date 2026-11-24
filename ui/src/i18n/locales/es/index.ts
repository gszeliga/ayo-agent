import type { Catalog } from '../../catalog'

import { chat } from './chat'
import { common } from './common'
import { connect } from './connect'
import { document } from './document'
import { documents } from './documents'
import { search } from './search'
import { settings } from './settings'
import { upload } from './upload'

export const es: Catalog = { chat, common, connect, document, documents, search, settings, upload }

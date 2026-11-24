import type { Catalog } from '../../catalog'

import { common } from './common'
import { connect } from './connect'
import { document } from './document'
import { documents } from './documents'
import { upload } from './upload'

export const es: Catalog = { common, connect, document, documents, upload }

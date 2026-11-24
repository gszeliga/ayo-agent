import { common } from './common'
import { connect } from './connect'
import { document } from './document'
import { documents } from './documents'
import { settings } from './settings'
import { upload } from './upload'

/** The source catalog: every other language is typed against it (`Catalog`). */
export const en = { common, connect, document, documents, settings, upload }

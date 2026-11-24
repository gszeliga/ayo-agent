import { common } from './common'
import { connect } from './connect'
import { document } from './document'
import { documents } from './documents'
import { upload } from './upload'

/** The source catalog: every other language is typed against it (`Catalog`). */
export const en = { common, connect, document, documents, upload }

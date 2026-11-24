import { common } from './common'
import { connect } from './connect'
import { documents } from './documents'

/** The source catalog: every other language is typed against it (`Catalog`). */
export const en = { common, connect, documents }

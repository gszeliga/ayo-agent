import type { Catalog } from '../../catalog'

import { common } from './common'
import { connect } from './connect'
import { documents } from './documents'

export const es: Catalog = { common, connect, documents }

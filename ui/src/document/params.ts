// The API's `{doc_id}` pattern (docs/openapi.json; params.test.ts checks it still matches):
// anything else is a 422 there, so it is "not found" here without a request.
export const DOC_ID_PATTERN = /^[a-z]+-[0-9a-f]{12}$/

export const CHUNK_PAGE_SIZE = 20

export type Tab = 'content' | 'chunks'
export type View = 'rendered' | 'raw'

export interface DetailParams {
  tab: Tab
  view: View
  /** 1-based page of chunks. */
  chunkPage: number
  /** How chunks show; raw by default: exactly the text that was embedded. */
  chunkView: View
}

/** The detail's state from the URL; invalid values fall back to the defaults. */
export function parseDetailParams(search: URLSearchParams): DetailParams {
  const cpage = search.get('cpage') ?? ''
  return {
    tab: search.get('tab') === 'chunks' ? 'chunks' : 'content',
    view: search.get('view') === 'raw' ? 'raw' : 'rendered',
    chunkPage: /^[1-9][0-9]{0,5}$/.test(cpage) ? Number(cpage) : 1,
    chunkView: search.get('cview') === 'rendered' ? 'rendered' : 'raw',
  }
}

/** Defaults left out; `view` only on the content tab, `cpage` and `cview` only on chunks. */
export function toDetailSearch(params: DetailParams): URLSearchParams {
  const search = new URLSearchParams()
  if (params.tab === 'chunks') {
    search.set('tab', 'chunks')
    if (params.chunkPage > 1) search.set('cpage', String(params.chunkPage))
    if (params.chunkView === 'rendered') search.set('cview', 'rendered')
  } else if (params.view === 'raw') {
    search.set('view', 'raw')
  }
  return search
}

/** Where "← Documents" goes: the list as the user left it, passed along by the list. */
export function backToList(state: unknown): string {
  const from = (state as { listSearch?: unknown } | null)?.listSearch
  return typeof from === 'string' && from.startsWith('?') ? `/documents${from}` : '/documents'
}

/** What the test search passes to a document it links to (location state, never the URL). */
export interface FromSearch {
  /** The search page's URL query (its options), `?` when none. */
  searchFrom: string
  /** The chunk the result was, outlined on the Chunks tab. */
  chunkIndex: number
}

/** What the test chat's trace passes to a document it links to (location state, never the
 * URL). */
export interface FromChat {
  /** The case's chat path (`/chat/<case id>`). */
  chatFrom: string
  /** The retrieved chunk, outlined on the Chunks tab; absent when no longer stored. */
  chunkIndex?: number
}

/** A case path and nothing else: location state is never trusted as a URL. */
const CHAT_CASE_PATH = /^\/chat\/[0-9a-f-]{36}$/

function chatFrom(state: unknown): string | null {
  const from = (state as Partial<FromChat> | null)?.chatFrom
  return typeof from === 'string' && CHAT_CASE_PATH.test(from) ? from : null
}

/** Where the page was opened from; its words are in the `document` catalog (`back.*`). */
export type BackTarget = 'documents' | 'search' | 'chat'

export interface BackLink {
  to: string
  target: BackTarget
}

/** Back to the chat or the search when the document was opened from one, else to the list. */
export function backLink(state: unknown): BackLink {
  const chat = chatFrom(state)
  if (chat !== null) return { to: chat, target: 'chat' }
  const from = (state as Partial<FromSearch> | null)?.searchFrom
  if (typeof from === 'string' && from.startsWith('?')) {
    return { to: from === '?' ? '/search' : `/search${from}`, target: 'search' }
  }
  return { to: backToList(state), target: 'documents' }
}

/** Where the outlined chunk was linked from, said above it (`chunks.highlight.*`). */
export function highlightSource(state: unknown): 'chat' | 'search' {
  return chatFrom(state) !== null ? 'chat' : 'search'
}

/** The chunk to outline: the one a search result or a chat trace linked to, if any. */
export function highlightedChunk(state: unknown): number | null {
  const index = (state as Partial<FromSearch> | null)?.chunkIndex
  return typeof index === 'number' && Number.isInteger(index) && index >= 0 ? index : null
}

/** The detail URL that shows a chunk: the Chunks tab on the chunk's page. */
export function chunkLink(docId: string, chunkIndex: number): string {
  const search = toDetailSearch({
    tab: 'chunks',
    view: 'rendered',
    chunkPage: Math.floor(chunkIndex / CHUNK_PAGE_SIZE) + 1,
    chunkView: 'raw',
  }).toString()
  return `/documents/${docId}?${search}`
}

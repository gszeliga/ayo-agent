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
}

/** The detail's state from the URL; invalid values fall back to the defaults. */
export function parseDetailParams(search: URLSearchParams): DetailParams {
  const cpage = search.get('cpage') ?? ''
  return {
    tab: search.get('tab') === 'chunks' ? 'chunks' : 'content',
    view: search.get('view') === 'raw' ? 'raw' : 'rendered',
    chunkPage: /^[1-9][0-9]{0,5}$/.test(cpage) ? Number(cpage) : 1,
  }
}

/** Defaults left out; the view only on the content tab, the chunk page only on chunks. */
export function toDetailSearch(params: DetailParams): URLSearchParams {
  const search = new URLSearchParams()
  if (params.tab === 'chunks') {
    search.set('tab', 'chunks')
    if (params.chunkPage > 1) search.set('cpage', String(params.chunkPage))
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

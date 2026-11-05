import type { paths } from '@/api/schema'

export type DocumentSort = NonNullable<
  NonNullable<paths['/admin/documents']['get']['parameters']['query']>['sort']
>

/** The prototype's sort options, in its order. */
export const SORT_OPTIONS: readonly { value: DocumentSort; label: string }[] = [
  { value: '-updated_at', label: 'Recently updated' },
  { value: 'updated_at', label: 'Least recently updated' },
  { value: '-created_at', label: 'Newest' },
  { value: 'created_at', label: 'Oldest' },
  { value: 'title', label: 'Title A–Z' },
  { value: '-title', label: 'Title Z–A' },
  { value: '-chunk_count', label: 'Most chunks' },
  { value: 'chunk_count', label: 'Fewest chunks' },
]

export const PAGE_SIZE = 25
// The API's own limits (docs/openapi.json; listParams.test.ts checks they still match), so a
// hand-edited URL never turns into a 422.
export const TENANT_PATTERN = /^[a-z0-9][a-z0-9-]{1,62}$/
export const Q_MAX_LENGTH = 200

export interface ListParams {
  tenant: string | null
  q: string
  sort: DocumentSort
  /** 1-based. */
  page: number
}

export const DEFAULT_PARAMS: ListParams = { tenant: null, q: '', sort: '-updated_at', page: 1 }

function isSort(value: string): value is DocumentSort {
  return SORT_OPTIONS.some((option) => option.value === value)
}

/** The list's state from the URL; invalid values fall back to their defaults. */
export function parseListParams(search: URLSearchParams): ListParams {
  const tenant = search.get('tenant')
  const q = search.get('q')?.trim() ?? ''
  const sort = search.get('sort') ?? ''
  const page = search.get('page') ?? ''
  return {
    tenant: tenant !== null && TENANT_PATTERN.test(tenant) ? tenant : null,
    q: q.length <= Q_MAX_LENGTH ? q : '',
    sort: isSort(sort) ? sort : DEFAULT_PARAMS.sort,
    page: /^[1-9][0-9]{0,6}$/.test(page) ? Number(page) : DEFAULT_PARAMS.page,
  }
}

/** The URL for a state: defaults left out, keys in a fixed order. */
export function toSearchParams(params: ListParams): URLSearchParams {
  const search = new URLSearchParams()
  if (params.tenant !== null) search.set('tenant', params.tenant)
  if (params.q) search.set('q', params.q)
  if (params.sort !== DEFAULT_PARAMS.sort) search.set('sort', params.sort)
  if (params.page !== DEFAULT_PARAMS.page) search.set('page', String(params.page))
  return search
}

export function hasFilters(params: ListParams): boolean {
  return params.tenant !== null || params.q !== ''
}

/** The API query for a state. */
export function toQuery(params: ListParams) {
  return {
    ...(params.tenant === null ? {} : { tenant: params.tenant }),
    ...(params.q ? { q: params.q } : {}),
    sort: params.sort,
    limit: PAGE_SIZE,
    offset: (params.page - 1) * PAGE_SIZE,
  }
}

/** The last page that has documents; 1 when there are none. */
export function lastPage(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE))
}

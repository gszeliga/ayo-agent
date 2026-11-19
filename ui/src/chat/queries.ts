import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

import type { Phase } from './phases'

type CaseListItem = components['schemas']['CaseListItem']

/** Cases per "Load more". */
export const CASES_PAGE_SIZE = 20
/** The API's limit on `q`. */
export const CASE_SEARCH_MAX_LENGTH = 200

export type CaseState = 'all' | 'open' | 'closed'

/**
 * The list's filters. Kept in memory only (decision: never in the URL): `q` searches what
 * happens on the floor, which is conversation content.
 */
export interface CaseFilters {
  q: string
  tenant: string | null
  phase: Phase | null
  state: CaseState
}

export const NO_FILTERS: CaseFilters = { q: '', tenant: null, phase: null, state: 'all' }

export function hasFilters(filters: CaseFilters): boolean {
  return (
    filters.q.trim() !== '' ||
    filters.tenant !== null ||
    filters.phase !== null ||
    filters.state !== 'all'
  )
}

/** The `list_cases` query for these filters; unset ones are left out. */
export function toQuery(filters: CaseFilters) {
  const q = filters.q.trim()
  return {
    ...(q && { q }),
    ...(filters.tenant !== null && { tenant: filters.tenant }),
    ...(filters.phase !== null && { phase: filters.phase }),
    ...(filters.state !== 'all' && { closed: filters.state === 'closed' }),
  }
}

/** The cases matching `filters`, newest update first, `CASES_PAGE_SIZE` more per page. */
export function useCases(filters: CaseFilters) {
  const client = useApiClient()
  return useInfiniteQuery({
    queryKey: ['cases', toQuery(filters)],
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        client.GET('/admin/cases', {
          params: { query: { ...toQuery(filters), limit: CASES_PAGE_SIZE, offset: pageParam } },
          signal,
        }),
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const next = last.offset + last.limit
      return next < last.total ? next : undefined
    },
    // The current rows stay (dimmed) while another filter loads.
    placeholderData: keepPreviousData,
  })
}

/**
 * The loaded pages as one list. A case updated between two pages moves to the top and can
 * show up again on a later page; it is kept once, where it was first seen.
 */
export function flattenCases(pages: { items: CaseListItem[] }[]): CaseListItem[] {
  const seen = new Set<string>()
  const cases: CaseListItem[] = []
  for (const page of pages) {
    for (const item of page.items) {
      if (seen.has(item.case_id)) continue
      seen.add(item.case_id)
      cases.push(item)
    }
  }
  return cases
}

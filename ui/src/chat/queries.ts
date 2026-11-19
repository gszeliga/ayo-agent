import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

import type { Phase } from './phases'

type CaseListItem = components['schemas']['CaseListItem']
type CaseDetail = components['schemas']['CaseDetail']

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

/** One case: header, facts, annotations, actions, AI summary, usage. */
export function caseKey(caseId: string) {
  return ['case', caseId] as const
}

export function useCase(caseId: string) {
  const client = useApiClient()
  return useQuery({
    queryKey: caseKey(caseId),
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/admin/cases/{case_id}', { params: { path: { case_id: caseId } }, signal }),
      ),
  })
}

/** Turns per page, both the latest one and each "Load earlier turns". */
export const TURNS_PAGE_SIZE = 20

export interface TurnsPageParam {
  offset: number
  limit: number
}

/** The page holding the latest turns of a case with `turns` turns (decision 13). */
export function latestTurnsPage(turns: number): TurnsPageParam {
  return { offset: Math.max(0, turns - TURNS_PAGE_SIZE), limit: TURNS_PAGE_SIZE }
}

/**
 * The page before one starting at `offset`, or undefined at the start. The last step asks
 * only for what is left, so no turn comes twice.
 */
export function earlierTurnsPage(offset: number): TurnsPageParam | undefined {
  if (offset <= 0) return undefined
  return {
    offset: Math.max(0, offset - TURNS_PAGE_SIZE),
    limit: Math.min(TURNS_PAGE_SIZE, offset),
  }
}

export function caseTurnsKey(caseId: string) {
  return ['case-turns', caseId] as const
}

/** The first page asked for: the latest, worked out from the case's turn count when fetched. */
const LATEST = 'latest'
type TurnsPage = TurnsPageParam | typeof LATEST
const FIRST_PAGE: TurnsPage = LATEST

/**
 * A case's turns, oldest first, loaded backwards from the latest page. Waits for `get_case`
 * (`ready`): the latest page is worked out from its turn count in the cache when fetched, so
 * a reset after re-reading the case starts from the new latest page. Turns are only ever
 * added at the end, so the offsets of the pages before it hold.
 */
export function useCaseTurns(caseId: string, ready: boolean) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useInfiniteQuery({
    queryKey: caseTurnsKey(caseId),
    enabled: ready,
    initialPageParam: FIRST_PAGE,
    queryFn: ({ pageParam, signal }) => {
      const query =
        pageParam === LATEST
          ? latestTurnsPage(queryClient.getQueryData<CaseDetail>(caseKey(caseId))?.turns ?? 0)
          : pageParam
      return unwrap(
        client.GET('/admin/cases/{case_id}/turns', {
          params: { path: { case_id: caseId }, query },
          signal,
        }),
      )
    },
    getNextPageParam: () => undefined,
    getPreviousPageParam: (first) => earlierTurnsPage(first.offset),
  })
}

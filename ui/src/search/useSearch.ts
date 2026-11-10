import { skipToken, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

import type { SearchOptions, SearchRequest } from './searchParams'

export type SearchResponse = components['schemas']['SearchResponse']

/** A search that answered: what the page shows, and what it shows again on coming back. */
export interface LastSearch {
  question: string
  options: SearchOptions
  request: SearchRequest
  response: SearchResponse
}

/**
 * The last search lives in the query cache under this key, set by hand and never fetched.
 * The cache is memory only and cleared whenever the connection changes, so results never
 * reach storage and Disconnect drops them.
 */
export const LAST_SEARCH_KEY = ['search', 'last'] as const

export function useLastSearch(): LastSearch | null {
  return (
    useQuery<LastSearch | null>({
      queryKey: LAST_SEARCH_KEY,
      queryFn: skipToken,
      // Kept while a document opened from the results is shown.
      gcTime: Infinity,
      staleTime: Infinity,
    }).data ?? null
  )
}

/**
 * One search. A mutation, not a query: each one is a paid call to the embedding provider,
 * so it runs only when asked, never on focus, and is never retried.
 */
export function useSearch() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (search: Omit<LastSearch, 'response'>): Promise<LastSearch> => ({
      ...search,
      response: await unwrap(client.POST('/admin/search', { body: search.request })),
    }),
    onSuccess: (last) => {
      queryClient.setQueryData<LastSearch | null>(LAST_SEARCH_KEY, last)
    },
    onError: () => {
      // The error replaces the results; coming back later must not show stale ones.
      queryClient.setQueryData<LastSearch | null>(LAST_SEARCH_KEY, null)
    },
  })
}

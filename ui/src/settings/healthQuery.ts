import { useIsFetching, useQuery, useQueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { ApiClient } from '@/api/client'
import { useApiClient } from '@/connection/context'

export const HEALTH_KEY = ['health'] as const
// The API keeps its own provider check for 60 s; asking again sooner only returns that.
const FRESH_MS = 60_000

const fetchHealth = (client: ApiClient, refresh: boolean, signal?: AbortSignal) =>
  unwrap(client.GET('/admin/health', { params: { query: { refresh } }, signal }))

/**
 * The services' status, shared by the header, the Services card and the upload dialog
 * (one query). Asked on load and on "Check now"; never polled. A window regaining focus
 * asks again once the answer is over a minute old.
 */
export function useServiceHealth() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: HEALTH_KEY,
    queryFn: ({ signal }) => fetchHealth(client, false, signal),
    staleTime: FRESH_MS,
  })
  const checking = useIsFetching({ queryKey: HEALTH_KEY }) > 0
  const checkNow = () =>
    queryClient.query({
      queryKey: HEALTH_KEY,
      queryFn: ({ signal }) => fetchHealth(client, true, signal),
      staleTime: 0,
    })
  return { ...query, checking, checkNow }
}

/** The last known status without asking (the upload dialog's warning). */
export function useCachedServiceHealth() {
  const client = useApiClient()
  return useQuery({
    queryKey: HEALTH_KEY,
    queryFn: ({ signal }) => fetchHealth(client, false, signal),
    enabled: false,
  }).data
}

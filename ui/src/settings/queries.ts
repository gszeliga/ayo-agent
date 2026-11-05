import { useQuery } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import { useApiClient } from '@/connection/context'

/** The current indexing settings and document counts (`GET /admin/settings`). */
export function useIndexingSettings() {
  const client = useApiClient()
  return useQuery({
    queryKey: ['settings'],
    queryFn: ({ signal }) => unwrap(client.GET('/admin/settings', { signal })),
  })
}

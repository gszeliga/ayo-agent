import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import { useApiClient } from '@/connection/context'

import { toQuery, type ListParams } from './listParams'

export function useDocuments(params: ListParams) {
  const client = useApiClient()
  return useQuery({
    queryKey: ['documents', params],
    queryFn: ({ signal }) =>
      unwrap(client.GET('/admin/documents', { params: { query: toQuery(params) }, signal })),
    // The current rows stay (dimmed) while the next page or filter loads.
    placeholderData: keepPreviousData,
  })
}

export function useTenants() {
  const client = useApiClient()
  return useQuery({
    queryKey: ['tenants'],
    queryFn: ({ signal }) => unwrap(client.GET('/admin/tenants', { signal })),
  })
}

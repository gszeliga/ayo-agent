import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { unwrap, type ApiClient } from '@/api/client'
import { useApiClient } from '@/connection/context'

import type { Target } from './bulkReprocess'
import { toQuery, type ListParams } from './listParams'

/** The API's largest page: what `fetchAllMatching` asks for. */
export const LIST_MAX_LIMIT = 100

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

/**
 * Every document matching the list's filters (all pages, in the list's order), fetched 100
 * at a time. Each page re-reads `total`, so documents added or removed meanwhile end it
 * early or late but never loop.
 */
export async function fetchAllMatching(
  client: ApiClient,
  params: ListParams,
  signal?: AbortSignal,
): Promise<Target[]> {
  const targets: Target[] = []
  const seen = new Set<string>()
  for (let offset = 0; ; offset += LIST_MAX_LIMIT) {
    const page = await unwrap(
      client.GET('/admin/documents', {
        params: { query: { ...toQuery(params), limit: LIST_MAX_LIMIT, offset } },
        signal,
      }),
    )
    for (const doc of page.items) {
      // A write between two pages can shift a document onto the next one.
      if (seen.has(doc.doc_id)) continue
      seen.add(doc.doc_id)
      targets.push({ docId: doc.doc_id, title: doc.title ?? doc.source_key })
    }
    if (page.items.length < LIST_MAX_LIMIT || offset + LIST_MAX_LIMIT >= page.total) {
      return targets
    }
  }
}

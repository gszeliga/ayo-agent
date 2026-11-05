import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

import { CHUNK_PAGE_SIZE } from './params'

type Document = components['schemas']['Document']
type DocumentPage = components['schemas']['DocumentPage']

const path = (docId: string) => ({ params: { path: { doc_id: docId } } })

/** The document; shown at once from the list's cache when it is there, then refreshed. */
export function useDocument(docId: string) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useQuery<Document>({
    queryKey: ['document', docId],
    queryFn: ({ signal }) =>
      unwrap(client.GET('/admin/documents/{doc_id}', { ...path(docId), signal })),
    placeholderData: () =>
      queryClient
        .getQueriesData<DocumentPage>({ queryKey: ['documents'] })
        .flatMap(([, page]) => page?.items ?? [])
        .find((doc) => doc.doc_id === docId),
  })
}

export function useContent(docId: string, enabled: boolean) {
  const client = useApiClient()
  return useQuery({
    queryKey: ['document', docId, 'content'],
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/admin/documents/{doc_id}/content', {
          ...path(docId),
          parseAs: 'text',
          signal,
        }),
      ),
    enabled,
  })
}

export function useChunks(docId: string, page: number, vectors: boolean, enabled: boolean) {
  const client = useApiClient()
  return useQuery({
    queryKey: ['document', docId, 'chunks', { page, vectors }],
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/admin/documents/{doc_id}/chunks', {
          params: {
            path: { doc_id: docId },
            query: {
              limit: CHUNK_PAGE_SIZE,
              offset: (page - 1) * CHUNK_PAGE_SIZE,
              include_embedding: vectors,
            },
          },
          signal,
        }),
      ),
    enabled,
    placeholderData: keepPreviousData,
  })
}

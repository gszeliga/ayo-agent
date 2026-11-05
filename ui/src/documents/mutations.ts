import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

type Document = components['schemas']['Document']
type DocumentPage = components['schemas']['DocumentPage']

/** The API's limit per bulk delete request. */
export const BULK_DELETE_BATCH = 100

const path = (docId: string) => ({ params: { path: { doc_id: docId } } })

/** Everything a write can make stale: lists, tenant counts, status counts. */
function refreshLists(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ['documents'] }),
    queryClient.invalidateQueries({ queryKey: ['tenants'] }),
    queryClient.invalidateQueries({ queryKey: ['settings'] }),
  ])
}

export function useRename(docId: string) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (title: string) =>
      unwrap(client.PATCH('/admin/documents/{doc_id}', { ...path(docId), body: { title } })),
    onSuccess: async (doc) => {
      // Known exactly: shown at once, then lists refetch (the title may change their order).
      queryClient.setQueryData<Document>(['document', docId], doc)
      queryClient.setQueriesData<DocumentPage>({ queryKey: ['documents'] }, (page) =>
        page
          ? { ...page, items: page.items.map((item) => (item.doc_id === docId ? doc : item)) }
          : page,
      )
      await queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}

export function useReprocess(docId: string) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (force: boolean) =>
      unwrap(
        client.POST('/admin/documents/{doc_id}/reprocess', {
          params: { path: { doc_id: docId }, query: { force } },
        }),
      ),
    onSuccess: async () => {
      // The document, its content and chunks (one key prefix), and the lists.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['document', docId] }),
        refreshLists(queryClient),
      ])
    },
  })
}

/** Removes a deleted document from the cache, so nothing shows it again. */
function forget(queryClient: QueryClient, docIds: string[]) {
  for (const docId of docIds) queryClient.removeQueries({ queryKey: ['document', docId] })
}

export function useDelete(docId: string) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(client.DELETE('/admin/documents/{doc_id}', path(docId))),
    // After a 404 too: it is gone either way.
    onSettled: async () => {
      forget(queryClient, [docId])
      await refreshLists(queryClient)
    },
  })
}

export interface BulkDeleteResult {
  deleted: components['schemas']['DeletedDocument'][]
  notFound: string[]
}

/** Some batches were deleted before one failed: what was done, and why it stopped. */
export class PartialBulkDeleteError extends Error {
  readonly done: BulkDeleteResult
  constructor(done: BulkDeleteResult, cause: unknown) {
    super(cause instanceof Error ? cause.message : 'bulk delete failed', { cause })
    this.name = 'PartialBulkDeleteError'
    this.done = done
  }
}

/** Deletes in batches of 100, one after the other; each batch is all or nothing. */
export function useBulkDelete() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (docIds: string[]): Promise<BulkDeleteResult> => {
      const done: BulkDeleteResult = { deleted: [], notFound: [] }
      for (let start = 0; start < docIds.length; start += BULK_DELETE_BATCH) {
        try {
          const result = await unwrap(
            client.POST('/admin/documents/delete', {
              body: { doc_ids: docIds.slice(start, start + BULK_DELETE_BATCH) },
            }),
          )
          done.deleted.push(...result.deleted)
          done.notFound.push(...result.not_found)
        } catch (error) {
          if (start === 0) throw error
          throw new PartialBulkDeleteError(done, error)
        }
      }
      return done
    },
    onSettled: async (result, error) => {
      const done = result ?? (error instanceof PartialBulkDeleteError ? error.done : null)
      if (done) forget(queryClient, [...done.deleted.map((d) => d.doc_id), ...done.notFound])
      await refreshLists(queryClient)
    },
  })
}

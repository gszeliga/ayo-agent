import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

import { caseKey } from './queries'

type CaseDetail = components['schemas']['CaseDetail']

const summaryKey = (caseId: string) => ['case-summary', caseId] as const

/**
 * Generates the case's AI summary (`POST /admin/cases/{case_id}/summary`): a real, billed
 * model call, so never retried. On success the stored summary shows at once and the case
 * is read again (its usage now counts the summary). The cache updates run from the
 * mutation's own options, so they happen even when the tab was left meanwhile.
 */
export function useGenerateSummary(caseId: string) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: summaryKey(caseId),
    mutationFn: () =>
      unwrap(
        client.POST('/admin/cases/{case_id}/summary', { params: { path: { case_id: caseId } } }),
      ),
    retry: false,
    onSuccess: async (summary) => {
      queryClient.setQueryData<CaseDetail>(caseKey(caseId), (old) =>
        old ? { ...old, summary } : old,
      )
      await queryClient.invalidateQueries({ queryKey: caseKey(caseId) })
    },
  })
}

/** Whether a summary of this case is being generated, by this view or one left meanwhile. */
export function useGeneratingSummary(caseId: string): boolean {
  return useIsMutating({ mutationKey: summaryKey(caseId) }) > 0
}

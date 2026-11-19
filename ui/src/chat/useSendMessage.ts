import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { useApiClient } from '@/connection/context'

import { caseKey, caseTurnsKey } from './queries'

type CaseTurnPage = components['schemas']['CaseTurnPage']
type CopilotMessageResponse = components['schemas']['CopilotMessageResponse']

export interface SendInput {
  sessionId: string
  tenant: string
  text: string
}

/**
 * Sends one message to the copilot (`POST /copilot/messages`): a real, billed model call,
 * so never retried. Once it answers, and before the "Sending…" bubble goes, the caches
 * catch up (decision 13): the case is read again, the new turn is fetched alone and added
 * after the loaded ones, and the list refreshes. These run from the mutation's own
 * options, so they still happen when the user has moved to another case meanwhile.
 */
export function useSendMessage() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SendInput): Promise<CopilotMessageResponse> =>
      unwrap(
        client.POST('/copilot/messages', {
          body: { session_id: input.sessionId, tenant: input.tenant, text: input.text },
        }),
      ),
    retry: false,
    onSuccess: async (response) => {
      const caseId = response.case_id
      void queryClient.invalidateQueries({ queryKey: ['cases'] })
      try {
        const [page] = await Promise.all([
          unwrap(
            client.GET('/admin/cases/{case_id}/turns', {
              params: { path: { case_id: caseId }, query: { offset: response.turn - 1, limit: 1 } },
            }),
          ),
          queryClient.invalidateQueries({ queryKey: caseKey(caseId) }),
        ])
        const [turn] = page.items
        if (turn === undefined) throw new Error('turn not found')
        queryClient.setQueryData<InfiniteData<CaseTurnPage>>(caseTurnsKey(caseId), (old) => {
          const last = old?.pages.at(-1)
          if (!old || !last || last.items.some((item) => item.turn === turn.turn)) return old
          return {
            ...old,
            pages: [
              ...old.pages.slice(0, -1),
              { ...last, items: [...last.items, turn], total: page.total },
            ],
          }
        })
      } catch {
        // The turn is stored; only the follow-up read failed. Load the latest page again.
        await queryClient.resetQueries({ queryKey: caseTurnsKey(caseId) })
      }
    },
  })
}

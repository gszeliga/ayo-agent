import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router'

import { ApiError } from '@/api/errors'
import type { components } from '@/api/schema'
import { LoadError } from '@/components/LoadError'
import { Skeleton } from '@/components/ui/skeleton'

import { CaseHeader } from './CaseHeader'
import { CaseNotFound } from './CaseNotFound'
import { caseTurnsKey, useCase, useCaseTurns } from './queries'
import { readOnlyReason } from './readOnly'
import { ReadOnlyNotice } from './ReadOnlyNotice'
import { TurnList } from './TurnList'

type CaseDetail = components['schemas']['CaseDetail']

/** An unknown case (404) or an id the API refuses (422): both mean there is no such case. */
function isMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422)
}

/**
 * `/chat/:caseId`: the case read-only (T2). The tab keeps the page's title: a case title is
 * conversation content, and the tab title reaches the browser's history.
 */
export function CaseView() {
  const { caseId = '' } = useParams()
  const detail = useCase(caseId)

  if (detail.isPending) {
    return (
      <div className="space-y-3" aria-label="Loading case">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-40" />
      </div>
    )
  }
  if (detail.isError) {
    if (isMissing(detail.error)) return <CaseNotFound />
    return (
      <LoadError
        error={detail.error}
        onRetry={() => {
          void detail.refetch()
        }}
      />
    )
  }
  // Keyed, so nothing of one case's view state carries over to the next.
  return (
    <LoadedCase
      key={caseId}
      caseId={caseId}
      detail={detail.data}
      refetch={() => detail.refetch()}
    />
  )
}

interface LoadedProps {
  caseId: string
  detail: CaseDetail
  refetch: () => Promise<unknown>
}

function LoadedCase({ caseId, detail, refetch }: LoadedProps) {
  const queryClient = useQueryClient()
  const turns = useCaseTurns(caseId, true)
  const [refreshing, setRefreshing] = useState(false)
  const reason = readOnlyReason(detail)

  async function refresh() {
    setRefreshing(true)
    try {
      await refetch()
      // Start again from the latest page: a turn added elsewhere is past the loaded offsets.
      await queryClient.resetQueries({ queryKey: caseTurnsKey(caseId) })
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <CaseHeader
        detail={detail}
        refreshing={refreshing}
        onRefresh={() => {
          void refresh()
        }}
      />
      {/* Reversed, so it opens at the newest turn and keeps its place when older ones load. */}
      <div className="flex min-h-0 flex-1 flex-col-reverse overflow-y-auto pr-1">
        <div className="py-2">
          <TurnList turns={turns} />
        </div>
      </div>
      {reason !== null && <ReadOnlyNotice reason={reason} />}
    </div>
  )
}

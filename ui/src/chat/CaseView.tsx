import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useParams } from 'react-router'

import { ApiError } from '@/api/errors'
import type { components } from '@/api/schema'
import { LoadError } from '@/components/LoadError'
import { Skeleton } from '@/components/ui/skeleton'

import { CaseHeader } from './CaseHeader'
import { useChatContext } from './chatContext'
import { CaseNotFound } from './CaseNotFound'
import { Composer } from './Composer'
import { InspectorDrawer, InspectorPanel } from './Inspector'
import { useWideScreen } from './inspectorState'
import { caseTurnsKey, useCase, useCaseTurns } from './queries'
import { readOnlyReason } from './readOnly'
import { ReadOnlyNotice } from './ReadOnlyNotice'
import { SendError } from './SendError'
import { TurnList } from './TurnList'
import { useChatInput } from './useChatInput'

type CaseDetail = components['schemas']['CaseDetail']

/** An unknown case (404) or an id the API refuses (422): both mean there is no such case. */
function isMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422)
}

/**
 * `/chat/:caseId`: the case, and its message box when it can be continued. The tab keeps the page's title: a case title is
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
  const { inspector } = useChatContext()
  const wide = useWideScreen()
  // The drawer is per case and starts closed; the column's hidden state is the page's.
  const [drawerOpen, setDrawerOpen] = useState(false)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const reason = readOnlyReason(detail)
  // A writable case always has its web session (readOnlyReason checks it).
  const input = useChatInput({ sessionId: detail.web_session_id ?? '', tenant: detail.tenant })

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

  const tabs = { detail, tab: inspector.tab, onTabChange: inspector.setTab }

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        <CaseHeader
          detail={detail}
          refreshing={refreshing}
          onRefresh={() => {
            void refresh()
          }}
          inspector={{
            wide,
            shown: !inspector.hidden,
            onToggle: () => {
              if (wide) inspector.setHidden(!inspector.hidden)
              else setDrawerOpen(true)
            },
          }}
          toggleRef={toggleRef}
        />
        {/* Reversed, so it opens at the newest turn and keeps its place when older ones load. */}
        <div className="flex min-h-0 flex-1 flex-col-reverse overflow-y-auto pr-1">
          <div className="py-2">
            <TurnList turns={turns} pending={input.pendingText} />
          </div>
        </div>
        {reason !== null ? (
          <ReadOnlyNotice reason={reason} />
        ) : (
          <div className="space-y-2">
            {input.error && !input.sending && (
              <SendError
                error={input.error}
                onSendAgain={input.submit}
                onReload={() => {
                  input.clearError()
                  void refresh()
                }}
              />
            )}
            <Composer
              value={input.text}
              onChange={input.setText}
              onSend={input.submit}
              sending={input.sending}
            />
          </div>
        )}
      </div>
      {wide ? (
        !inspector.hidden && (
          <InspectorPanel width={inspector.width} onResize={inspector.setWidth} {...tabs} />
        )
      ) : (
        <InspectorDrawer
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          returnFocusTo={toggleRef}
          {...tabs}
        />
      )}
    </div>
  )
}

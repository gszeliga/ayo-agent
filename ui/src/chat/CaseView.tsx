import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import { ApiError } from '@/api/errors'
import type { components } from '@/api/schema'
import { LoadError } from '@/components/LoadError'
import { Skeleton } from '@/components/ui/skeleton'

import { CaseHeader } from './CaseHeader'
import { useChatContext } from './chatContext'
import { CaseNotFound } from './CaseNotFound'
import { DeleteCaseDialog } from './DeleteCaseDialog'
import { ExportDialog } from './ExportDialog'
import { Composer } from './Composer'
import { InspectorDrawer, InspectorPanel } from './Inspector'
import { InspectorRail } from './InspectorRail'
import { useWideScreen, type InspectorTab, type TraceFocus } from './inspectorState'
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
  const { t } = useTranslation('chat')
  const { caseId = '' } = useParams()
  const detail = useCase(caseId)

  if (detail.isPending) {
    return (
      <div className="space-y-3" aria-label={t('page.loadingCase')}>
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
  // Where the drawer gives focus back: the button that opened it (a rail button, a chip).
  const focusReturn = useRef<HTMLElement | null>(null)
  const [dialog, setDialog] = useState<'export' | 'delete' | null>(null)
  // The Trace tab's open entries and the one opened from a chip: per case, kept while tabs
  // switch (the tab itself unmounts).
  const [traceOpen, setTraceOpen] = useState<ReadonlySet<number> | null>(null)
  const [traceFocus, setTraceFocus] = useState<TraceFocus | null>(null)
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

  // The newest loaded turn: the Trace tab's entry open by default.
  const newestTurn = turns.data?.pages.at(-1)?.items.at(-1)?.turn
  const defaultOpen = () => new Set(newestTurn !== undefined ? [newestTurn] : [])

  /** Shows the inspector (the column, or the drawer when narrow), on `tab` if given. */
  function openInspector(tab?: InspectorTab) {
    if (tab) inspector.setTab(tab)
    if (wide) {
      inspector.setHidden(false)
    } else {
      const active = document.activeElement
      focusReturn.current = active instanceof HTMLElement ? active : null
      setDrawerOpen(true)
    }
  }

  function showTrace(turn: number) {
    openInspector('trace')
    setTraceOpen((open) => new Set([...(open ?? defaultOpen()), turn]))
    setTraceFocus((focus) => ({ turn, nonce: (focus?.nonce ?? 0) + 1 }))
  }

  const tabs = {
    detail,
    tab: inspector.tab,
    onTabChange: inspector.setTab,
    trace: {
      turns,
      open: traceOpen,
      setOpen: (turn: number, isOpen: boolean) => {
        setTraceOpen((open) => {
          // Until now only the newest was open (by default): start from that.
          const next = new Set(open ?? defaultOpen())
          if (isOpen) next.add(turn)
          else next.delete(turn)
          return next
        })
      },
      focus: traceFocus,
    },
  }

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        <CaseHeader
          detail={detail}
          refreshing={refreshing}
          onRefresh={() => {
            void refresh()
          }}
          onExport={() => {
            setDialog('export')
          }}
          onDelete={() => {
            setDialog('delete')
          }}
        />
        {/* Reversed, so it opens at the newest turn and keeps its place when older ones load. */}
        <div className="flex min-h-0 flex-1 flex-col-reverse overflow-y-auto pr-1">
          <div className="py-2">
            <TurnList turns={turns} pending={input.pendingText} onShowTrace={showTrace} />
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
      {wide && !inspector.hidden ? (
        <InspectorPanel
          width={inspector.width}
          onResize={inspector.setWidth}
          onHide={() => {
            inspector.setHidden(true)
          }}
          {...tabs}
        />
      ) : (
        <InspectorRail detail={detail} drawer={!wide} onOpen={openInspector} />
      )}
      {!wide && (
        <InspectorDrawer
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          returnFocusTo={focusReturn}
          {...tabs}
        />
      )}
      <ExportDialog
        detail={detail}
        open={dialog === 'export'}
        onOpenChange={(open) => {
          setDialog(open ? 'export' : null)
        }}
      />
      <DeleteCaseDialog
        detail={detail}
        open={dialog === 'delete'}
        onOpenChange={(open) => {
          setDialog(open ? 'delete' : null)
        }}
      />
    </div>
  )
}

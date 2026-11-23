import { Suspense, useState } from 'react'
import { Outlet, useNavigate, useParams } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/paths'

import { CasesList, CasesRail } from './CasesList'
import type { ChatContext, Draft } from './chatContext'
import type { InspectorTab } from './inspectorState'
import { saveLastTenant } from './lastTenant'
import { NewConversationDialog } from './NewConversationDialog'
import { hasFilters, NO_FILTERS, useCases, type CaseFilters } from './queries'
import { newSessionId } from './sessionId'

/** How long the search waits after typing pauses, as on the documents list. */
export const SEARCH_DEBOUNCE_MS = 300

/**
 * `/chat`, `/chat/new` and `/chat/:caseId`: the cases list beside the selected case or a
 * new conversation. A layout route, so the filters, the loaded pages, the collapsed list and
 * a new conversation's draft survive switching views. Nothing here goes in the URL but the
 * case id, nor in browser storage but the last tenant's name. The inspector's state (hidden,
 * its tab) lives here too, so it survives switching cases.
 */
export function ChatPage() {
  useDocumentTitle('Test chat')
  const { caseId } = useParams()
  const [filters, setFilters] = useState<CaseFilters>(NO_FILTERS)
  const [collapsed, setCollapsed] = useState(false)
  const q = useDebouncedValue(filters.q, SEARCH_DEBOUNCE_MS)
  const applied = { ...filters, q }
  const cases = useCases(applied)
  const total = cases.data?.pages.at(-1)?.total
  const navigate = useNavigate()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [inspectorHidden, setInspectorHidden] = useState(false)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('state')

  function openNewConversation() {
    setDialogOpen(true)
  }

  function start(tenant: string) {
    saveLastTenant(tenant)
    setDraft({ sessionId: newSessionId(), tenant })
    setDialogOpen(false)
    void navigate(ROUTES.chatNew)
  }

  const context: ChatContext = {
    draft,
    clearDraft: () => {
      setDraft(null)
    },
    openNewConversation,
    inspector: {
      hidden: inspectorHidden,
      setHidden: setInspectorHidden,
      tab: inspectorTab,
      setTab: setInspectorTab,
    },
  }

  return (
    <div className="flex h-full min-h-0 gap-4">
      <aside
        aria-label="Cases list"
        className={cn('flex-none border-r pr-4', collapsed ? 'w-auto' : 'w-80')}
      >
        {collapsed ? (
          <CasesRail
            total={total}
            onNewConversation={openNewConversation}
            onExpand={() => {
              setCollapsed(false)
            }}
          />
        ) : (
          <CasesList
            filters={filters}
            cases={cases}
            filtered={hasFilters(applied)}
            onFiltersChange={setFilters}
            selectedCaseId={caseId}
            onNewConversation={openNewConversation}
            onCollapse={() => {
              setCollapsed(true)
            }}
          />
        )}
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* The routes inside are lazy too: only they wait, not the list. */}
        <Suspense fallback={<Skeleton aria-label="Loading case" className="h-40" />}>
          <Outlet context={context} />
        </Suspense>
      </div>
      <NewConversationDialog open={dialogOpen} onOpenChange={setDialogOpen} onStart={start} />
    </div>
  )
}

/** `/chat` with no case selected. */
export function NoCaseSelected() {
  return (
    <EmptyState
      as="h1"
      title="Pick a case"
      description="Choose a case from the list, or start a new conversation."
      className="mt-10"
    />
  )
}

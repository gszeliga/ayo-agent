import { Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
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
import { PanelResizer } from './PanelResizer'
import {
  CASES_LIMITS,
  CASES_WIDTH_KEY,
  INSPECTOR_LIMITS,
  INSPECTOR_WIDTH_KEY,
  loadWidth,
  saveWidth,
} from './panelWidth'
import { hasFilters, NO_FILTERS, useCases, type CaseFilters } from './queries'
import { newSessionId } from './sessionId'

/** How long the search waits after typing pauses, as on the documents list. */
export const SEARCH_DEBOUNCE_MS = 300

/**
 * `/chat`, `/chat/new` and `/chat/:caseId`: the cases list beside the selected case or a
 * new conversation. A layout route, so the filters, the loaded pages, the collapsed list and
 * a new conversation's draft survive switching views. Nothing here goes in the URL but the
 * case id, nor in browser storage but the last tenant's name and the two column widths (numbers,
 * `panelWidth.ts`). The inspector's state (hidden, its tab, its width) lives here too, so it
 * survives switching cases.
 */
export function ChatPage() {
  const { t } = useTranslation('chat')
  useDocumentTitle(t('pageTitle'))
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
  const [inspectorWidth, setInspectorWidth] = useState(() =>
    loadWidth(INSPECTOR_WIDTH_KEY, INSPECTOR_LIMITS),
  )
  const [casesWidth, setCasesWidth] = useState(() => loadWidth(CASES_WIDTH_KEY, CASES_LIMITS))

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
      width: inspectorWidth,
      setWidth: (width) => {
        setInspectorWidth(width)
        saveWidth(INSPECTOR_WIDTH_KEY, width)
      },
    },
  }

  return (
    <div className="flex h-full min-h-0 gap-4">
      <aside
        aria-label={t('page.casesList')}
        style={collapsed ? undefined : { width: casesWidth }}
        className={cn(
          'relative flex flex-none',
          collapsed ? 'w-auto' : 'max-w-[40%] min-w-60 flex-col pr-4',
        )}
      >
        {!collapsed && (
          <PanelResizer
            label={t('page.resizeCasesList')}
            edge="right"
            width={casesWidth}
            limits={CASES_LIMITS}
            onResize={(width) => {
              setCasesWidth(width)
              saveWidth(CASES_WIDTH_KEY, width)
            }}
          />
        )}
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
        <Suspense fallback={<Skeleton aria-label={t('page.loadingCase')} className="h-40" />}>
          <Outlet context={context} />
        </Suspense>
      </div>
      <NewConversationDialog open={dialogOpen} onOpenChange={setDialogOpen} onStart={start} />
    </div>
  )
}

/** `/chat` with no case selected. */
export function NoCaseSelected() {
  const { t } = useTranslation('chat')
  return (
    <EmptyState
      as="h1"
      title={t('page.pickTitle')}
      description={t('page.pickDescription')}
      className="mt-10"
    />
  )
}

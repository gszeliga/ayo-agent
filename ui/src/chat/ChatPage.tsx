import { Suspense, useState } from 'react'
import { Outlet, useParams } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'

import { CasesList, CasesRail } from './CasesList'
import { hasFilters, NO_FILTERS, useCases, type CaseFilters } from './queries'

/** How long the search waits after typing pauses, as on the documents list. */
export const SEARCH_DEBOUNCE_MS = 300

/**
 * `/chat` and `/chat/:caseId`: the cases list beside the selected case. A layout route, so
 * the filters, the loaded pages and the collapsed list survive switching cases. Nothing
 * here goes in the URL or in browser storage but the case id in the path.
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

  return (
    <div className="flex h-full min-h-0 gap-4">
      <aside
        aria-label="Cases list"
        className={cn('flex-none border-r pr-4', collapsed ? 'w-auto' : 'w-80')}
      >
        {collapsed ? (
          <CasesRail
            total={total}
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
            onCollapse={() => {
              setCollapsed(true)
            }}
          />
        )}
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* The routes inside are lazy too: only they wait, not the list. */}
        <Suspense fallback={<Skeleton aria-label="Loading case" className="h-40" />}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  )
}

/** `/chat` with no case selected. */
export function NoCaseSelected() {
  return (
    <EmptyState
      as="h1"
      title="Pick a case"
      description="Choose a case from the list to read its conversation."
      className="mt-10"
    />
  )
}

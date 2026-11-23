import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/StateMessage'
import { LoadError } from '@/components/LoadError'
import { useTenants } from '@/documents/queries'
import { cn } from '@/lib/utils'

import { CaseFiltersBar } from './CaseFiltersBar'
import { CaseRow } from './CaseRow'
import { PanelButton, PanelRail, PanelToggle } from './PanelToggle'
import { flattenCases, NO_FILTERS, type CaseFilters, type useCases } from './queries'

interface Props {
  /** The filters as typed (the search not yet debounced). */
  filters: CaseFilters
  /** The query for the debounced filters. */
  cases: ReturnType<typeof useCases>
  /** Whether the debounced filters filter anything. */
  filtered: boolean
  onFiltersChange: (filters: CaseFilters) => void
  selectedCaseId: string | undefined
  onCollapse: () => void
  onNewConversation: () => void
}

/** The cases column: filters, rows, Load more, and its empty, loading and error states. */
export function CasesList({
  filters,
  cases,
  filtered,
  onFiltersChange,
  selectedCaseId,
  onCollapse,
  onNewConversation,
}: Props) {
  const tenants = useTenants()
  const items = cases.data ? flattenCases(cases.data.pages) : []
  const total = cases.data?.pages.at(-1)?.total

  return (
    <section aria-labelledby="cases-heading" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 pb-3">
        <h2 id="cases-heading" className="font-semibold">
          Cases
          {total !== undefined && (
            <span className="text-muted-foreground ml-2 text-sm font-normal tabular-nums">
              {total}
            </span>
          )}
        </h2>
        <PanelToggle side="left" noun="cases" expanded onClick={onCollapse} />
      </div>
      <Button className="mb-3 w-full" onClick={onNewConversation}>
        <Plus aria-hidden="true" />
        New conversation
      </Button>
      <CaseFiltersBar filters={filters} tenants={tenants.data} onChange={onFiltersChange} />
      <div className="-mx-1 mt-3 min-h-0 flex-1 overflow-y-auto px-1 pb-2">
        {cases.isPending ? (
          <div className="space-y-2" aria-label="Loading cases">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : cases.isError && !cases.data ? (
          <LoadError
            error={cases.error}
            onRetry={() => {
              void cases.refetch()
            }}
          />
        ) : items.length === 0 ? (
          filtered ? (
            <EmptyState
              title="No cases match"
              description="Try another search or filter."
              action={
                <Button
                  variant="outline"
                  onClick={() => {
                    onFiltersChange(NO_FILTERS)
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="No conversations yet"
              description="Cases appear here once someone talks to the copilot."
            />
          )
        ) : (
          <>
            <ul
              aria-label="Cases"
              className={cn('space-y-1', cases.isPlaceholderData && 'opacity-60')}
            >
              {items.map((item) => (
                <li key={item.case_id}>
                  <CaseRow item={item} selected={item.case_id === selectedCaseId} />
                </li>
              ))}
            </ul>
            {cases.isFetchNextPageError && (
              <div className="mt-2">
                <ErrorState
                  message="More cases could not be loaded."
                  onRetry={() => {
                    void cases.fetchNextPage()
                  }}
                />
              </div>
            )}
            {cases.hasNextPage && !cases.isFetchNextPageError && (
              <Button
                variant="outline"
                className="mt-2 w-full"
                disabled={cases.isFetchingNextPage}
                onClick={() => {
                  void cases.fetchNextPage()
                }}
              >
                {cases.isFetchingNextPage ? 'Loading…' : 'Load more'}
              </Button>
            )}
          </>
        )}
      </div>
    </section>
  )
}

/** The collapsed list, on the left edge: Show cases, New conversation and the case count. */
export function CasesRail({
  total,
  onExpand,
  onNewConversation,
}: {
  total: number | undefined
  onExpand: () => void
  onNewConversation: () => void
}) {
  return (
    <PanelRail side="left" label="Cases list (collapsed)">
      <PanelToggle side="left" noun="cases" expanded={false} onClick={onExpand} />
      <PanelButton
        side="left"
        variant="default"
        label="New conversation"
        onClick={onNewConversation}
      >
        <Plus aria-hidden="true" />
      </PanelButton>
      {total !== undefined && (
        <span className="text-muted-foreground text-xs tabular-nums">
          {total}
          <span className="sr-only"> cases</span>
        </span>
      )}
    </PanelRail>
  )
}

import { Loader2, RefreshCw, Search, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { LoadError } from '@/components/LoadError'
import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { LazyUploadDialog } from '@/upload/LazyUploadDialog'

import { DocumentsTable, DocumentsTableSkeleton } from './DocumentsTable'
import {
  hasFilters,
  lastPage,
  NO_FILTERS,
  parseListParams,
  Q_MAX_LENGTH,
  SORT_OPTIONS,
  STATUS_OPTIONS,
  toSearchParams,
  type DocumentSort,
  type ListParams,
  type StatusFilter,
} from './listParams'
import { Pagination } from './Pagination'
import { useDocuments, useTenants } from './queries'
import { BulkDeleteDialog } from './BulkDeleteDialog'
import { BulkReprocessDialog, type ReprocessSource } from './BulkReprocessDialog'
import { SelectionBar } from './SelectionBar'
import { TenantSelect, TenantSidebar } from './TenantFilter'
import { useSelection } from './useSelection'

export const SEARCH_DELAY_MS = 300

export function DocumentsPage() {
  useDocumentTitle('Documents')
  const [searchParams, setSearchParams] = useSearchParams()
  const params = parseListParams(searchParams)
  const canonical = toSearchParams(params).toString()
  const documents = useDocuments(params)
  const tenants = useTenants()
  const [uploading, setUploading] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  // Set while the reprocess dialog is open; the source is fixed when it opens.
  const [reprocessing, setReprocessing] = useState<ReprocessSource | null>(null)
  // Kept across pages and sorts; a new tenant, search or status starts a new one.
  const selection = useSelection(
    `${params.tenant ?? ''}\u0000${params.q}\u0000${params.status ?? ''}`,
  )
  const uploadButton = (
    <Button
      onClick={() => {
        setUploading(true)
      }}
    >
      <Upload aria-hidden="true" />
      Upload
    </Button>
  )

  /** Filters and sort start again at page 1; `replace` keeps history entries for real steps. */
  function update(changes: Partial<ListParams>, { replace = false } = {}) {
    setSearchParams(toSearchParams({ ...params, page: 1, ...changes }), { replace })
  }

  // A hand-edited URL with invalid values is corrected in place.
  useEffect(() => {
    if (searchParams.toString() !== canonical) setSearchParams(canonical, { replace: true })
  }, [searchParams, canonical, setSearchParams])

  // A page past the end (documents deleted meanwhile) moves to the last one.
  const total = documents.data?.total
  const beyondEnd =
    total !== undefined && !documents.isPlaceholderData && params.page > lastPage(total)
  useEffect(() => {
    if (beyondEnd) {
      setSearchParams(toSearchParams({ ...params, page: lastPage(total) }), { replace: true })
    }
  })

  // The search box updates the URL once typing pauses, without a history entry per key.
  const [qDraft, setQDraft] = useState(params.q)
  const [syncedQ, setSyncedQ] = useState(params.q)
  if (params.q !== syncedQ) {
    // The URL changed elsewhere (Back, Clear filters): show its value.
    setSyncedQ(params.q)
    setQDraft(params.q)
  }
  useEffect(() => {
    if (qDraft.trim() === params.q) return
    const timer = setTimeout(() => {
      update({ q: qDraft.trim() }, { replace: true })
    }, SEARCH_DELAY_MS)
    return () => {
      clearTimeout(timer)
    }
  })

  const data = documents.data
  return (
    <div className="flex gap-8">
      <TenantSidebar tenants={tenants.data} params={params} />
      <section className="min-w-0 flex-1 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <h1 className="text-xl font-semibold">Documents</h1>
            {data && (
              <p className="text-muted-foreground tabular-nums">
                {data.total === 1 ? '1 document' : `${String(data.total)} documents`}
              </p>
            )}
          </div>
          {uploadButton}
        </div>
        {selection.items.size > 0 ? (
          <SelectionBar
            count={selection.items.size}
            offPage={
              selection.items.size -
              (data?.items.filter((doc) => selection.has(doc.doc_id)).length ?? 0)
            }
            onClear={selection.clear}
            onReprocess={() => {
              setReprocessing({ kind: 'selection', items: selection.items })
            }}
            onDelete={() => {
              setBulkDeleting(true)
            }}
          />
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <TenantSelect tenants={tenants.data} params={params} />
            <div className="relative min-w-56 flex-1">
              <Search
                aria-hidden="true"
                className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2"
              />
              <label htmlFor="q" className="sr-only">
                Search title or file name
              </label>
              <Input
                id="q"
                type="search"
                className="pl-9"
                placeholder="Search title or file name"
                maxLength={Q_MAX_LENGTH}
                value={qDraft}
                onChange={(event) => {
                  setQDraft(event.target.value)
                }}
              />
            </div>
            <label htmlFor="status" className="sr-only">
              Status
            </label>
            <select
              id="status"
              className="border-input bg-card h-9 rounded-md border px-3"
              value={params.status ?? ''}
              onChange={(event) => {
                update({ status: (event.target.value || null) as StatusFilter | null })
              }}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <label htmlFor="sort" className="sr-only">
              Sort
            </label>
            <select
              id="sort"
              className="border-input bg-card h-9 rounded-md border px-3"
              value={params.sort}
              onChange={(event) => {
                update({ sort: event.target.value as DocumentSort })
              }}
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {hasFilters(params) && (
              <Button
                variant="ghost"
                onClick={() => {
                  update(NO_FILTERS)
                }}
              >
                Clear filters
              </Button>
            )}
            {params.status === 'outdated' &&
              data &&
              data.total > 0 &&
              !documents.isPlaceholderData && (
                <Button
                  variant="outline"
                  onClick={() => {
                    setReprocessing({ kind: 'filter', params, total: data.total })
                  }}
                >
                  <RefreshCw aria-hidden="true" />
                  Reprocess all {data.total} outdated
                </Button>
              )}
            {documents.isFetching && data && (
              <Loader2
                role="status"
                aria-label="Loading"
                className="text-muted-foreground size-4 animate-spin"
              />
            )}
          </div>
        )}

        {documents.isError && !data ? (
          <LoadError error={documents.error} onRetry={() => void documents.refetch()} />
        ) : !data ? (
          <DocumentsTableSkeleton />
        ) : data.total === 0 ? (
          hasFilters(params) ? (
            <EmptyState
              title="No documents match"
              description="Try another search, tenant or status."
              action={
                <Button
                  variant="outline"
                  onClick={() => {
                    update(NO_FILTERS)
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="No documents yet"
              description="Upload a Markdown document to make it available to the copilot."
              action={uploadButton}
            />
          )
        ) : (
          <>
            <div className="bg-card rounded-xl border">
              <DocumentsTable
                documents={data.items}
                busy={documents.isPlaceholderData}
                now={documents.dataUpdatedAt}
                selection={selection}
              />
            </div>
            <Pagination
              page={params.page}
              total={data.total}
              shown={data.items.length}
              onPage={(page) => {
                update({ page })
              }}
            />
          </>
        )}
      </section>
      <BulkDeleteDialog
        selected={selection.items}
        open={bulkDeleting}
        onOpenChange={setBulkDeleting}
        onDeleted={selection.remove}
      />
      {reprocessing && (
        <BulkReprocessDialog
          source={reprocessing}
          open
          onOpenChange={(open) => {
            if (!open) setReprocessing(null)
          }}
          onFinished={selection.remove}
        />
      )}
      <LazyUploadDialog
        mode={{ kind: 'upload', defaultTenant: params.tenant }}
        open={uploading}
        onOpenChange={setUploading}
      />
    </div>
  )
}

import { Loader2, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useConnection } from '@/connection/context'

import { DocumentsTable, DocumentsTableSkeleton } from './DocumentsTable'
import {
  DEFAULT_PARAMS,
  hasFilters,
  lastPage,
  parseListParams,
  Q_MAX_LENGTH,
  SORT_OPTIONS,
  toSearchParams,
  type DocumentSort,
  type ListParams,
} from './listParams'
import { Pagination } from './Pagination'
import { useDocuments, useTenants } from './queries'
import { TenantSelect, TenantSidebar } from './TenantFilter'

export const SEARCH_DELAY_MS = 300

function errorMessage(error: Error, baseUrl: string): string {
  if (error instanceof ApiError && error.isNetworkError) {
    return `Can't reach the API at ${baseUrl}. Check the URL and that the API is running.`
  }
  return error.message
}

export function DocumentsPage() {
  const { connection } = useConnection()
  const [searchParams, setSearchParams] = useSearchParams()
  const params = parseListParams(searchParams)
  const canonical = toSearchParams(params).toString()
  const documents = useDocuments(params)
  const tenants = useTenants()

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
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-xl font-semibold">Documents</h1>
          {data && (
            <p className="text-muted-foreground tabular-nums">
              {data.total === 1 ? '1 document' : `${String(data.total)} documents`}
            </p>
          )}
        </div>
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
                update({ tenant: DEFAULT_PARAMS.tenant, q: DEFAULT_PARAMS.q })
              }}
            >
              Clear filters
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

        {documents.isError && !data ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
              <span>{errorMessage(documents.error, connection?.baseUrl ?? '')}</span>
              <Button
                variant="outline"
                onClick={() => {
                  void documents.refetch()
                }}
              >
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        ) : !data ? (
          <DocumentsTableSkeleton />
        ) : data.total === 0 ? (
          <div className="bg-card rounded-xl border p-10 text-center">
            {hasFilters(params) ? (
              <>
                <h2 className="font-semibold">No documents match</h2>
                <p className="text-muted-foreground mt-1">Try another search or tenant.</p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => {
                    update({ tenant: null, q: '' })
                  }}
                >
                  Clear filters
                </Button>
              </>
            ) : (
              <>
                <h2 className="font-semibold">No documents yet</h2>
                <p className="text-muted-foreground mt-1">
                  Uploaded Markdown documents will be listed here.
                </p>
              </>
            )}
          </div>
        ) : (
          <>
            <div className="bg-card rounded-xl border">
              <DocumentsTable
                documents={data.items}
                busy={documents.isPlaceholderData}
                now={documents.dataUpdatedAt}
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
    </div>
  )
}

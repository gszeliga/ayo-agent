import { ArrowLeft, FileUp } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router'

import { CopyButton } from '@/components/CopyButton'
import { LoadError } from '@/components/LoadError'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { StatusBadge } from '@/documents/StatusBadge'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { LazyUploadDialog } from '@/upload/LazyUploadDialog'

import { ChunksTab } from './ChunksTab'
import { ContentTab } from './ContentTab'
import { DeleteDialog } from './DeleteDialog'
import { FactsPanel } from './FactsPanel'
import { isNotFound } from './errors'
import { DocumentNotFound } from './NotFound'
import {
  backToList,
  DOC_ID_PATTERN,
  parseDetailParams,
  toDetailSearch,
  type DetailParams,
  type Tab,
} from './params'
import { useDocument } from './queries'
import { ReprocessButton } from './ReprocessButton'
import { TitleEditor } from './TitleEditor'

export function DocumentPage() {
  const { docId = '' } = useParams()
  const location = useLocation()
  const back = backToList(location.state)
  if (!DOC_ID_PATTERN.test(docId)) return <DocumentNotFound back={back} />
  // Keyed by id: another document starts with fresh state.
  return <DocumentDetail key={docId} docId={docId} back={back} />
}

function DocumentDetail({ docId, back }: { docId: string; back: string }) {
  const state: unknown = useLocation().state
  const [searchParams, setSearchParams] = useSearchParams()
  const params = parseDetailParams(searchParams)
  const document = useDocument(docId)
  // A tab that finds the document gone (deleted meanwhile) says so for the whole page.
  const [gone, setGone] = useState(false)
  const [replacing, setReplacing] = useState(false)
  const doc = document.data
  const title = doc ? (doc.title ?? doc.source_key) : null

  useDocumentTitle(title)

  function update(changes: Partial<DetailParams>) {
    // `replace`: switching views is not a step worth a history entry; the location state
    // (the list's filters, for "← Documents") is kept.
    setSearchParams(toDetailSearch({ ...params, ...changes }), {
      replace: true,
      state,
    })
  }

  if (gone || isNotFound(document.error)) return <DocumentNotFound back={back} />

  return (
    <div className="space-y-5">
      <Link
        to={back}
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-[13px]"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        Documents
      </Link>

      {document.isError && !doc ? (
        <LoadError error={document.error} onRetry={() => void document.refetch()} />
      ) : !doc ? (
        <div aria-busy="true" aria-label="Loading document" className="space-y-3">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </div>
      ) : (
        <>
          <header className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <TitleEditor
                doc={doc}
                onGone={() => {
                  setGone(true)
                }}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setReplacing(true)
                  }}
                >
                  <FileUp aria-hidden="true" />
                  Replace
                </Button>
                <ReprocessButton
                  docId={docId}
                  onGone={() => {
                    setGone(true)
                  }}
                />
                <DeleteDialog doc={doc} back={back} />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge document={doc} />
              <span className="bg-secondary text-muted-foreground rounded-sm px-2 py-0.5 text-xs font-medium">
                {doc.tenant}
              </span>
              <span className="text-muted-foreground flex items-center font-mono text-[12.5px]">
                {doc.doc_id}
                <CopyButton value={doc.doc_id} label="Copy doc_id" />
              </span>
            </div>
          </header>

          <div className="flex flex-col gap-6 lg:flex-row-reverse lg:items-start">
            <div className="lg:w-80 lg:flex-none">
              <FactsPanel
                document={doc}
                now={document.dataUpdatedAt || Date.parse(doc.updated_at)}
              />
            </div>
            <Tabs
              className="min-w-0 flex-1"
              value={params.tab}
              onValueChange={(tab) => {
                update({ tab: tab as Tab, chunkPage: 1 })
              }}
            >
              <TabsList>
                <TabsTrigger value="content">Content</TabsTrigger>
                <TabsTrigger value="chunks">Chunks</TabsTrigger>
              </TabsList>
              {/* Radix mounts only the active tab, so each fetches when first opened. */}
              <TabsContent value="content" className="pt-3">
                <ContentTab
                  docId={docId}
                  view={params.view}
                  onView={(view) => {
                    update({ view })
                  }}
                  onGone={() => {
                    setGone(true)
                  }}
                />
              </TabsContent>
              <TabsContent value="chunks" className="pt-3">
                <ChunksTab
                  docId={docId}
                  page={params.chunkPage}
                  onPage={(chunkPage) => {
                    update({ chunkPage })
                  }}
                  view={params.chunkView}
                  onView={(chunkView) => {
                    update({ chunkView })
                  }}
                  onGone={() => {
                    setGone(true)
                  }}
                />
              </TabsContent>
            </Tabs>
          </div>
          <LazyUploadDialog
            mode={{ kind: 'replace', document: doc }}
            open={replacing}
            onOpenChange={setReplacing}
          />
        </>
      )}
    </div>
  )
}

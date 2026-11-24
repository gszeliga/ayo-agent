import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { LoadError } from '@/components/LoadError'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { ChunkCard } from './ChunkCard'
import { isNotFound } from './errors'
import { CHUNK_PAGE_SIZE, type View } from './params'
import { useChunks } from './queries'
import { ViewToggle } from './ViewToggle'

export function ChunksTab({
  docId,
  onGone,
  page,
  onPage,
  view,
  onView,
  highlight = null,
  highlightSource,
}: {
  docId: string
  /** The chunk a search result or a chat trace linked to: outlined and scrolled to. */
  highlight?: number | null
  /** Where the outlined chunk was linked from, said above it. */
  highlightSource?: 'search' | 'chat'
  /** The document was deleted meanwhile (a 404). */
  onGone: () => void
  page: number
  onPage: (page: number) => void
  view: View
  onView: (view: View) => void
}) {
  const { t } = useTranslation('document')
  // A debug aid, kept out of the URL so a shared link never loads vectors.
  const [vectors, setVectors] = useState(false)
  const chunks = useChunks(docId, page, vectors, true)
  const gone = isNotFound(chunks.error)
  useEffect(() => {
    if (gone) onGone()
  }, [gone, onGone])
  const data = chunks.data
  const from = (page - 1) * CHUNK_PAGE_SIZE + 1
  const lastPage = data ? Math.max(1, Math.ceil(data.total / CHUNK_PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <ViewToggle view={view} onView={onView} label={t('chunks.viewLabel')} order="raw-first" />
        <label className="flex w-fit items-center gap-2 text-[13px]">
          <input
            type="checkbox"
            checked={vectors}
            onChange={(event) => {
              setVectors(event.target.checked)
            }}
          />
          {t('chunks.showVectors')}
          <span className="bg-warning-muted text-warning rounded-sm px-1.5 py-0.5 text-[11px] font-semibold">
            {t('chunks.debugBadge')}
          </span>
        </label>
      </div>
      {chunks.isError && !data ? (
        <LoadError error={chunks.error} onRetry={() => void chunks.refetch()} />
      ) : !data ? (
        <div aria-busy="true" aria-label={t('chunks.loading')} className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : data.total === 0 ? (
        <p className="text-muted-foreground">{t('chunks.none')}</p>
      ) : (
        <>
          <div
            aria-busy={chunks.isPlaceholderData}
            className={cn('space-y-3', chunks.isPlaceholderData && 'opacity-60')}
          >
            {data.items.map((chunk) => (
              <ChunkCard
                key={chunk.chunk_index}
                chunk={chunk}
                view={view}
                highlighted={chunk.chunk_index === highlight}
                highlightSource={highlightSource}
              />
            ))}
          </div>
          <nav
            aria-label={t('chunks.pagesLabel')}
            className="flex items-center justify-between gap-4"
          >
            <p className="text-muted-foreground tabular-nums">
              {t('chunks.range', { from, to: from + data.items.length - 1, total: data.total })}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={page <= 1}
                onClick={() => {
                  onPage(page - 1)
                }}
              >
                {t('chunks.previous')}
              </Button>
              <Button
                variant="outline"
                disabled={page >= lastPage}
                onClick={() => {
                  onPage(page + 1)
                }}
              >
                {t('chunks.next')}
              </Button>
            </div>
          </nav>
        </>
      )}
    </div>
  )
}

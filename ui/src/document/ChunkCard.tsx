import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'
import { cn } from '@/lib/utils'

import { LazyMarkdown } from './LazyMarkdown'
import type { View } from './params'

type Chunk = components['schemas']['Chunk']

const VECTOR_PREVIEW = 12

/** One chunk. Rendered, each chunk is a document of its own: a table or code block the
 * splitter cut stays inside its card. */
export function ChunkCard({
  chunk,
  view,
  highlighted = false,
  highlightSource = 'search',
}: {
  chunk: Chunk
  view: View
  /** The chunk a search result or a chat trace linked to. */
  highlighted?: boolean
  /** Where it was linked from, said above it when highlighted. */
  highlightSource?: 'search' | 'chat'
}) {
  const { t } = useTranslation('document')
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    if (highlighted) ref.current?.scrollIntoView({ block: 'center' })
  }, [highlighted])
  return (
    <article
      ref={ref}
      aria-label={t('chunks.card', { index: chunk.chunk_index })}
      data-highlighted={highlighted || undefined}
      className={cn(
        'bg-card space-y-2 rounded-xl border p-4',
        highlighted && 'border-primary ring-primary ring-1',
      )}
    >
      {highlighted && (
        <p className="text-primary text-[12px] font-semibold">
          {t(`chunks.highlight.${highlightSource}`)}
        </p>
      )}
      <header className="text-muted-foreground flex flex-wrap items-baseline gap-x-3 text-[13px]">
        <span className="text-foreground font-mono font-semibold">#{chunk.chunk_index}</span>
        {chunk.heading && <span className="min-w-0 flex-1 truncate">{chunk.heading}</span>}
        <span className="ml-auto tabular-nums">{t('chunks.chars', { n: chunk.char_count })}</span>
      </header>
      {view === 'rendered' ? (
        <LazyMarkdown source={chunk.chunk_text} />
      ) : (
        <p className="whitespace-pre-wrap">{chunk.chunk_text}</p>
      )}
      {chunk.embedding && (
        <div className="bg-secondary flex items-center gap-2 rounded-md px-2.5 py-1.5">
          <code className="text-muted-foreground min-w-0 flex-1 truncate font-mono text-[12px]">
            [
            {chunk.embedding
              .slice(0, VECTOR_PREVIEW)
              .map((v) => v.toFixed(4))
              .join(', ')}
            , … {t('chunks.values', { n: chunk.embedding.length })}]
          </code>
          <CopyButton value={JSON.stringify(chunk.embedding)} label={t('chunks.copyVector')} />
        </div>
      )}
    </article>
  )
}

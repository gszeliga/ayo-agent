import { useState } from 'react'
import { Link, useLocation } from 'react-router'

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { chunkLink, type FromSearch } from '@/document/params'

import { isLong } from './format'

type SearchHit = components['schemas']['SearchHitResult']

/** One chunk found: how close, which document, where in it, and its text. */
export function ResultCard({ hit, embedderConfig }: { hit: SearchHit; embedderConfig: string }) {
  const [expanded, setExpanded] = useState(false)
  const { search } = useLocation()
  const title = hit.document_title ?? hit.source_key
  const long = isLong(hit.chunk_text)
  const state: FromSearch = { searchFrom: search || '?', chunkIndex: hit.chunk_index }
  // The bar shows 0 to 1; a negative similarity (opposite direction) leaves it empty.
  const width = `${String(Math.max(0, Math.min(1, hit.similarity)) * 100)}%`

  return (
    <li aria-label={`Result ${String(hit.rank)}`} className="bg-card rounded-xl border p-4">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="bg-secondary text-muted-foreground rounded-sm px-1.5 py-0.5 font-mono text-[12px] font-semibold">
          #{hit.rank}
        </span>
        <span className="inline-flex items-center gap-2">
          <span
            aria-hidden="true"
            className="bg-secondary h-1.5 w-24 overflow-hidden rounded-full border"
          >
            <span className="bg-primary block h-full" style={{ width }} />
          </span>
          <span className="font-mono text-[13px] font-semibold tabular-nums">
            <span className="sr-only">Similarity </span>
            {hit.similarity.toFixed(4)}
          </span>
        </span>
        <Link
          to={chunkLink(hit.doc_id, hit.chunk_index)}
          state={state}
          className="min-w-0 font-semibold hover:underline"
        >
          {title}
        </Link>
        <span className="bg-secondary text-muted-foreground rounded-sm px-2 py-0.5 text-xs font-medium">
          {hit.tenant}
        </span>
        {hit.embedder_outdated && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="warning" tabIndex={0}>
                Other model
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Embedded with another model than {embedderConfig}: this similarity is not comparable.
              Reprocess the document.
            </TooltipContent>
          </Tooltip>
        )}
        <span className="text-muted-foreground ml-auto text-[12.5px] whitespace-nowrap tabular-nums">
          {hit.char_count} chars
        </span>
      </div>
      <div className="text-muted-foreground mb-2 flex flex-wrap gap-x-2 gap-y-0.5 text-[13px]">
        <span className={hit.heading ? undefined : 'italic'}>
          {hit.heading ?? 'Before the first heading'}
        </span>
        <span className="font-mono text-[12px]">
          {hit.source_key} · chunk {hit.chunk_index}
        </span>
      </div>
      <p className={long && !expanded ? 'line-clamp-3 whitespace-pre-wrap' : 'whitespace-pre-wrap'}>
        {hit.chunk_text}
      </p>
      {long && (
        <button
          type="button"
          aria-expanded={expanded}
          className="text-link mt-1.5 text-[13px] font-medium hover:underline"
          onClick={() => {
            setExpanded(!expanded)
          }}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </li>
  )
}

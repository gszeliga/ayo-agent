import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { chunkLink, type FromSearch } from '@/document/params'
import { useLanguage } from '@/layout/languageContext'
import { formatDecimal } from '@/lib/format'

import { isLong } from './format'

type SearchHit = components['schemas']['SearchHitResult']

/** One chunk found: how close, which document, where in it, and its text. */
export function ResultCard({ hit, embedderConfig }: { hit: SearchHit; embedderConfig: string }) {
  const { t } = useTranslation('search')
  const { language } = useLanguage()
  const [expanded, setExpanded] = useState(false)
  const { search } = useLocation()
  const title = hit.document_title ?? hit.source_key
  const long = isLong(hit.chunk_text)
  const state: FromSearch = { searchFrom: search || '?', chunkIndex: hit.chunk_index }
  // The bar shows 0 to 1; a negative similarity (opposite direction) leaves it empty.
  const width = `${String(Math.max(0, Math.min(1, hit.similarity)) * 100)}%`

  return (
    <li
      aria-label={t('result.label', { rank: hit.rank })}
      className="bg-card rounded-xl border p-4"
    >
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
            <span className="sr-only">{t('result.similarity')} </span>
            {formatDecimal(hit.similarity, language, { min: 4 })}
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
                {t('result.otherModel')}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              {t('result.otherModelHint', { config: embedderConfig })}
            </TooltipContent>
          </Tooltip>
        )}
        <span className="text-muted-foreground ml-auto text-[12.5px] whitespace-nowrap tabular-nums">
          {t('result.chars', { n: hit.char_count })}
        </span>
      </div>
      <div className="text-muted-foreground mb-2 flex flex-wrap gap-x-2 gap-y-0.5 text-[13px]">
        <span className={hit.heading ? undefined : 'italic'}>
          {hit.heading ?? t('result.noHeading')}
        </span>
        <span className="font-mono text-[12px]">
          {hit.source_key} · {t('result.chunk', { index: hit.chunk_index })}
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
          {expanded ? t('result.less') : t('result.more')}
        </button>
      )}
    </li>
  )
}

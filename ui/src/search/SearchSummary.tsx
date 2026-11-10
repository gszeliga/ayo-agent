import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

import { tenantsSummary } from './format'
import type { LastSearch } from './useSearch'

const ms = (value: number) => `${value.toFixed(1)} ms`

/** The count, the scope, the timings and, folded away, how the search ran. */
export function SearchSummary({ last }: { last: LastSearch }) {
  const [open, setOpen] = useState(false)
  const { response, options } = last
  const count = response.results.length
  const scope = [
    `top ${String(options.topK)}`,
    ...(options.minSimilarity !== null ? [`min ${String(options.minSimilarity)}`] : []),
    options.tenants.length > 0 ? tenantsSummary(options.tenants) : 'all tenants',
    ...(options.includeOutdated ? ['other models included'] : []),
  ].join(' · ')
  const debug = response.debug
  const rows: [string, string, boolean][] = debug
    ? [
        [`Embedded query (input_type: ${debug.input_type})`, debug.embedded_query, false],
        ['Embedder config searched', debug.embedder_config, true],
        ['Current chunker config', debug.chunker_config, true],
        ['Skipped (embedder_mismatch)', String(response.skipped.embedder_mismatch), false],
      ]
    : []

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-2.5">
      <div
        role="status"
        aria-label="Search summary"
        className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]"
      >
        <span className="text-foreground font-semibold">
          {count} {count === 1 ? 'result' : 'results'}
        </span>
        <span>{scope}</span>
        {debug && (
          <span className="font-mono text-[12px]">
            Embedding {ms(debug.timings_ms.embed)} · Search {ms(debug.timings_ms.search)} · Total{' '}
            {ms(debug.timings_ms.total)}
          </span>
        )}
        {debug && (
          <CollapsibleTrigger className="text-link inline-flex items-center gap-1 font-medium hover:underline">
            Details
            <ChevronDown
              aria-hidden="true"
              className={cn('size-3.5 transition-transform', open && 'rotate-180')}
            />
          </CollapsibleTrigger>
        )}
      </div>
      <CollapsibleContent>
        <dl className="bg-card divide-y rounded-xl border px-4 text-[13px]">
          {rows.map(([label, value, mono]) => (
            <div key={label} className="flex flex-wrap justify-between gap-x-4 gap-y-1 py-2">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className={cn('min-w-0 text-right break-all', mono && 'font-mono text-[12px]')}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </CollapsibleContent>
    </Collapsible>
  )
}

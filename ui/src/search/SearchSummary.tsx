import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useLanguage } from '@/layout/languageContext'
import { formatDecimal } from '@/lib/format'
import { cn } from '@/lib/utils'

import { tenantsSummary } from './format'
import type { LastSearch } from './useSearch'

/** The count, the scope, the timings and, folded away, how the search ran. */
export function SearchSummary({ last }: { last: LastSearch }) {
  const { t } = useTranslation('search')
  const { language } = useLanguage()
  const [open, setOpen] = useState(false)
  const { response, options } = last
  const count = response.results.length
  const ms = (value: number) => t('summary.ms', { n: formatDecimal(value, language, { min: 1 }) })
  const scope = [
    t('summary.top', { n: options.topK }),
    ...(options.minSimilarity !== null
      ? [
          t('summary.min', {
            n: formatDecimal(options.minSimilarity, language, { min: 0, max: 15 }),
          }),
        ]
      : []),
    options.tenants.length > 0
      ? tenantsSummary(options.tenants, language)
      : t('summary.allTenants'),
    ...(options.includeOutdated ? [t('summary.otherModels')] : []),
  ].join(' · ')
  const debug = response.debug
  const rows: [string, string, boolean][] = debug
    ? [
        [t('summary.embeddedQuery', { type: debug.input_type }), debug.embedded_query, false],
        [t('summary.embedderConfig'), debug.embedder_config, true],
        [t('summary.chunkerConfig'), debug.chunker_config, true],
        [t('summary.skipped'), String(response.skipped.embedder_mismatch), false],
      ]
    : []

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-2.5">
      <div
        role="status"
        aria-label={t('summary.label')}
        className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]"
      >
        <span className="text-foreground font-semibold">{t('summary.results', { count })}</span>
        <span>{scope}</span>
        {debug && (
          <span className="font-mono text-[12px]">
            {t('summary.timings', {
              embed: ms(debug.timings_ms.embed),
              search: ms(debug.timings_ms.search),
              total: ms(debug.timings_ms.total),
            })}
          </span>
        )}
        {debug && (
          <CollapsibleTrigger className="text-link inline-flex items-center gap-1 font-medium hover:underline">
            {t('summary.details')}
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

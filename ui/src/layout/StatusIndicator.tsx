import { useTranslation } from 'react-i18next'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { ServiceDetails, StatusDot } from '@/settings/ServiceDetails'
import { useServiceHealth } from '@/settings/healthQuery'

import { summarizeHealth } from './healthSummary'

/**
 * One pill in the header: "All systems ok", the service that is down, or why it isn't known;
 * the details in a popover. Its name keeps each service's state for screen readers.
 */
export function StatusIndicator() {
  const health = useServiceHealth()
  const { t } = useTranslation()
  const database = health.data?.database.status ?? 'unknown'
  const embeddings = health.data?.embeddings.status ?? 'unknown'
  const summary = summarizeHealth(health.data, health.isPending)
  const down = summary === 'databaseDown' || summary === 'embeddingsDown' || summary === 'bothDown'
  const dot = summary === 'ok' ? 'up' : down ? 'down' : 'unknown'
  return (
    <Popover>
      <PopoverTrigger
        aria-label={t('status.trigger', {
          database: t(`status.state.${database}`),
          embeddings: t(`status.state.${embeddings}`),
        })}
        className={cn(
          'hover:bg-accent flex min-h-8 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium whitespace-nowrap',
          summary === 'ok' && 'text-success',
          down && 'bg-danger-muted text-destructive border-destructive/40 hover:bg-danger-muted/80',
          !down && summary !== 'ok' && 'text-muted-foreground',
        )}
      >
        <StatusDot state={dot} />
        <span className="hidden md:inline">{t(`status.summary.${summary}`)}</span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <ServiceDetails />
      </PopoverContent>
    </Popover>
  )
}

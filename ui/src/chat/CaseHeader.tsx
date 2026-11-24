import { Download, RefreshCw, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/layout/languageContext'
import { cn } from '@/lib/utils'

import { formatCost, formatTokens } from './format'
import { PhaseStepper } from './PhaseStepper'

type CaseDetail = components['schemas']['CaseDetail']

interface Props {
  detail: CaseDetail
  refreshing: boolean
  onRefresh: () => void
  onExport: () => void
  onDelete: () => void
}

/**
 * Title, tenant, turns, what the case used; Refresh, Export and Delete; the stepper.
 * Export and Delete work on read-only cases too. The inspector has its own toggle.
 */
export function CaseHeader({ detail, refreshing, onRefresh, onExport, onDelete }: Props) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  const { cost, total_tokens: tokens } = detail.usage
  const facts = [
    detail.tenant,
    t('turns', { count: detail.turns }),
    ...(cost !== null ? [formatCost(cost, language)] : []),
    ...(tokens !== null ? [formatTokens(tokens, language)] : []),
  ]
  return (
    <header className="space-y-3 border-b pb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1
            className={cn(
              'truncate text-lg font-semibold',
              detail.title === null && 'text-muted-foreground italic',
            )}
          >
            {detail.title ?? t('untitled')}
          </h1>
          <p className="text-muted-foreground text-[13px]" data-testid="case-facts">
            {facts.join(' · ')}
          </p>
        </div>
        <div className="flex flex-none flex-wrap justify-end gap-2">
          <Button variant="outline" disabled={refreshing} onClick={onRefresh}>
            <RefreshCw aria-hidden="true" className={cn(refreshing && 'animate-spin')} />
            {t('header.refresh')}
          </Button>
          <Button variant="outline" onClick={onExport} aria-haspopup="dialog">
            <Download aria-hidden="true" />
            {t('header.export')}
          </Button>
          <Button
            variant="outline"
            className="text-destructive"
            onClick={onDelete}
            aria-haspopup="dialog"
          >
            <Trash2 aria-hidden="true" />
            {t('header.delete')}
          </Button>
        </div>
      </div>
      <PhaseStepper phase={detail.phase} />
    </header>
  )
}

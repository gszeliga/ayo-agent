import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { useLanguage } from '@/layout/languageContext'

import { outdatedReasonLabel } from './status'

type Document = components['schemas']['Document']

/** Green "Indexed", or amber "Outdated" with the reason in a tooltip (and for screen readers). */
export function StatusBadge({
  document,
}: {
  document: Pick<Document, 'status' | 'outdated_reason'>
}) {
  const { t } = useTranslation('documents')
  const { language } = useLanguage()
  if (document.status === 'indexed') {
    return <Badge variant="success">{t('status.indexed')}</Badge>
  }
  const reason = outdatedReasonLabel(document.outdated_reason ?? 'unknown', language)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="warning" tabIndex={0}>
          {t('status.outdated')}
          <span className="sr-only">: {reason}</span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  )
}

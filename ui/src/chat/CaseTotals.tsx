import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { useLanguage } from '@/layout/languageContext'

import { turnsUsage, usageLine } from './trace'

type CaseDetail = components['schemas']['CaseDetail']

/** What the whole case used: the total, then the turns and the AI summary apart. */
export function CaseTotals({ detail }: { detail: CaseDetail }) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  return (
    <section
      aria-labelledby="case-totals"
      className="bg-secondary/50 space-y-1 rounded-md px-3 py-2"
    >
      <h2 id="case-totals" className="text-sm font-semibold">
        {t('totals.title')}
      </h2>
      <p className="text-sm" data-testid="case-total">
        {usageLine(detail.usage, language)}
      </p>
      <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 text-xs">
        <dt>{t('totals.turns')}</dt>
        <dd data-testid="turns-usage">{usageLine(turnsUsage(detail), language)}</dd>
        {detail.summary && (
          <>
            <dt>{t('totals.summary')}</dt>
            <dd data-testid="summary-usage">{usageLine(detail.summary.usage, language)}</dd>
          </>
        )}
      </dl>
    </section>
  )
}

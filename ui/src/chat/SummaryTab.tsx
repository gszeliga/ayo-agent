import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { describeError } from '@/api/errors'
import type { components } from '@/api/schema'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { LazyMarkdown } from '@/document/LazyMarkdown'
import { i18n } from '@/i18n'
import { useLanguage } from '@/layout/languageContext'
import { formatUtc, relativeTime } from '@/lib/format'
import type { Language } from '@/lib/language'
import { useCopilotSettings } from '@/settings/queries'

import { GenerateSummaryDialog } from './GenerateSummaryDialog'
import { StructuredSummary } from './StructuredSummary'
import { describeSummaryError } from './summaryErrors'
import { usageLine } from './trace'
import { useGenerateSummary, useGeneratingSummary } from './useGenerateSummary'

type CaseDetail = components['schemas']['CaseDetail']

/** The structured summary (always), then the stored AI summary and its generation. */
export function SummaryTab({ detail }: { detail: CaseDetail }) {
  return (
    <div className="space-y-6">
      <StructuredSummary detail={detail} />
      <AiSummary detail={detail} />
    </div>
  )
}

/** A failed summary in `language` (decision 16: kept as the error, worded when shown). */
function summaryErrorMessage(error: Error, language: Language): string {
  const t = i18n.getFixedT(language, 'chat')
  const problem = describeSummaryError(error)
  if (problem.code === 'modelFailed') return t('summaryError.modelFailed', { type: problem.type })
  // Not a network error (that is `unreachable`), so the address is never used.
  if (problem.code === 'other') return describeError(problem.error, '', language)
  return t(`summaryError.${problem.code}`)
}

function AiSummary({ detail }: { detail: CaseDetail }) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  // Read now, so the dialog names the model at once; cached for the session (decision 40).
  const copilot = useCopilotSettings()
  const generate = useGenerateSummary(detail.case_id)
  const generating = useGeneratingSummary(detail.case_id)
  const [asking, setAsking] = useState(false)
  const { summary } = detail
  const empty = detail.turns === 0

  return (
    <section aria-labelledby="ai-summary" aria-busy={generating} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ai-summary" className="text-sm font-semibold">
          {t('totals.summary')}
        </h2>
        <Button
          variant="outline"
          size="sm"
          disabled={generating || empty}
          onClick={() => {
            setAsking(true)
          }}
        >
          <Sparkles aria-hidden="true" />
          {generating
            ? t('aiSummary.generating')
            : summary
              ? t('aiSummary.regenerate')
              : t('aiSummary.generate')}
        </Button>
      </div>
      {empty && <p className="text-muted-foreground text-xs">{t('aiSummary.nothingYet')}</p>}
      {generate.error && !generating && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{summaryErrorMessage(generate.error, language)}</AlertDescription>
        </Alert>
      )}
      {generating ? (
        <div aria-label={t('aiSummary.loading')} className="space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : summary ? (
        <div className="space-y-2">
          {summary.stale && (
            <p role="note" className="bg-warning-muted text-warning rounded-md px-3 py-2 text-xs">
              <Badge variant="warning" className="mr-2">
                {t('aiSummary.stale')}
              </Badge>
              {t('aiSummary.staleNote', { from: summary.source_version, now: detail.version })}
            </p>
          )}
          <div className="bg-card rounded-md border px-3 py-2 text-sm">
            <LazyMarkdown source={summary.content} />
          </div>
          <p className="text-muted-foreground text-xs" data-testid="summary-meta">
            <code className="font-mono break-all">{summary.model}</code> ·{' '}
            <time dateTime={summary.generated_at} title={formatUtc(summary.generated_at)}>
              {relativeTime(summary.generated_at, language)}
            </time>{' '}
            · {t('aiSummary.version', { n: summary.source_version })} ·{' '}
            {usageLine(summary.usage, language)}
          </p>
        </div>
      ) : (
        !empty && <p className="text-muted-foreground text-sm italic">{t('aiSummary.none')}</p>
      )}
      <GenerateSummaryDialog
        open={asking}
        onOpenChange={setAsking}
        replacing={summary !== null}
        copilot={copilot}
        onGenerate={() => {
          setAsking(false)
          generate.mutate()
        }}
      />
    </section>
  )
}

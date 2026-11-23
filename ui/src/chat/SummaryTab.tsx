import { Sparkles } from 'lucide-react'
import { useState } from 'react'

import type { components } from '@/api/schema'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { LazyMarkdown } from '@/document/LazyMarkdown'
import { formatUtc, relativeTime } from '@/lib/format'
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

function AiSummary({ detail }: { detail: CaseDetail }) {
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
          AI summary
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
          {generating ? 'Generating…' : summary ? 'Regenerate' : 'Generate AI summary'}
        </Button>
      </div>
      {empty && (
        <p className="text-muted-foreground text-xs">Nothing to summarise until the first turn.</p>
      )}
      {generate.error && !generating && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{describeSummaryError(generate.error)}</AlertDescription>
        </Alert>
      )}
      {generating ? (
        <div aria-label="Generating the summary" className="space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : summary ? (
        <div className="space-y-2">
          {summary.stale && (
            <p role="note" className="bg-warning-muted text-warning rounded-md px-3 py-2 text-xs">
              <Badge variant="warning" className="mr-2">
                Stale
              </Badge>
              Made from version {summary.source_version}; the case is at version {detail.version}{' '}
              now. Regenerate to include what changed.
            </p>
          )}
          <div className="bg-card rounded-md border px-3 py-2 text-sm">
            <LazyMarkdown source={summary.content} />
          </div>
          <p className="text-muted-foreground text-xs" data-testid="summary-meta">
            <code className="font-mono break-all">{summary.model}</code> ·{' '}
            <time dateTime={summary.generated_at} title={formatUtc(summary.generated_at)}>
              {relativeTime(summary.generated_at)}
            </time>{' '}
            · version {summary.source_version} · {usageLine(summary.usage)}
          </p>
        </div>
      ) : (
        !empty && <p className="text-muted-foreground text-sm italic">No AI summary yet.</p>
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

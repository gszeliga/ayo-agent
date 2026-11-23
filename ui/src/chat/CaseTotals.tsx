import type { components } from '@/api/schema'

import { turnsUsage, usageLine } from './trace'

type CaseDetail = components['schemas']['CaseDetail']

/** What the whole case used: the total, then the turns and the AI summary apart. */
export function CaseTotals({ detail }: { detail: CaseDetail }) {
  return (
    <section
      aria-labelledby="case-totals"
      className="bg-secondary/50 space-y-1 rounded-md px-3 py-2"
    >
      <h2 id="case-totals" className="text-sm font-semibold">
        Case totals
      </h2>
      <p className="text-sm" data-testid="case-total">
        {usageLine(detail.usage)}
      </p>
      <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 text-xs">
        <dt>Turns</dt>
        <dd data-testid="turns-usage">{usageLine(turnsUsage(detail))}</dd>
        {detail.summary && (
          <>
            <dt>AI summary</dt>
            <dd data-testid="summary-usage">{usageLine(detail.summary.usage)}</dd>
          </>
        )}
      </dl>
    </section>
  )
}

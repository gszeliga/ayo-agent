import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { LoadError } from '@/components/LoadError'
import { Skeleton } from '@/components/ui/skeleton'

import { CaseTotals } from './CaseTotals'
import { EarlierTurns } from './EarlierTurns'
import type { TraceView } from './inspectorState'
import { TraceEntry } from './TraceEntry'

type CaseDetail = components['schemas']['CaseDetail']

/**
 * The case's totals, then one entry per loaded turn, newest first (the conversation's own
 * pages: no request of its own but "Load earlier turns"). The newest is open until the
 * user opens or closes one.
 */
export function TraceTab({ detail, trace }: { detail: CaseDetail; trace: TraceView }) {
  const { t } = useTranslation('chat')
  const { turns } = trace
  const items = turns.data ? turns.data.pages.flatMap((page) => page.items).reverse() : []
  const newest = items[0]?.turn
  const isOpen = (turn: number) => (trace.open === null ? turn === newest : trace.open.has(turn))

  return (
    <div className="space-y-4">
      <CaseTotals detail={detail} />
      <p className="text-muted-foreground text-xs">{t('trace.neverShown')}</p>
      {turns.isPending ? (
        <Skeleton aria-label={t('trace.loading')} className="h-24" />
      ) : turns.isError && !turns.data ? (
        <LoadError
          error={turns.error}
          onRetry={() => {
            void turns.refetch()
          }}
        />
      ) : items.length === 0 ? (
        <p className="text-muted-foreground text-sm italic">{t('trace.none')}</p>
      ) : (
        <>
          <ol aria-label={t('trace.list')} className="space-y-2">
            {items.map((turn) => (
              <TraceEntry
                key={turn.turn}
                caseId={detail.case_id}
                turn={turn}
                open={isOpen(turn.turn)}
                onOpenChange={(open) => {
                  trace.setOpen(turn.turn, open)
                }}
                focused={trace.focus?.turn === turn.turn}
                focusNonce={trace.focus?.nonce}
              />
            ))}
          </ol>
          <div className="flex justify-center">
            <EarlierTurns turns={turns} />
          </div>
        </>
      )}
    </div>
  )
}

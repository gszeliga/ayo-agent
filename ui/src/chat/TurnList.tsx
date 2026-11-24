import { useTranslation } from 'react-i18next'

import { LoadError } from '@/components/LoadError'
import { Skeleton } from '@/components/ui/skeleton'

import { EarlierTurns } from './EarlierTurns'
import { PendingTurn } from './PendingTurn'
import type { useCaseTurns } from './queries'
import { TurnBlock } from './TurnBlock'

interface Props {
  turns: ReturnType<typeof useCaseTurns>
  /** A message being answered, shown after the turns until the turn is stored. */
  pending?: string | null
  /** Opens a turn's trace in the inspector. */
  onShowTrace?: (turn: number) => void
}

/** The conversation, oldest first, with "Load earlier turns" above it. */
export function TurnList({ turns, pending = null, onShowTrace }: Props) {
  const { t } = useTranslation('chat')
  if (turns.isPending) {
    return (
      <div className="space-y-4" aria-label={t('turnList.loading')}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    )
  }
  if (turns.isError && !turns.data) {
    return (
      <LoadError
        error={turns.error}
        onRetry={() => {
          void turns.refetch()
        }}
      />
    )
  }
  const items = turns.data.pages.flatMap((page) => page.items)
  return (
    <div className="space-y-5">
      <div className="flex justify-center">
        <EarlierTurns turns={turns} />
      </div>
      <div role="log" aria-live="polite" aria-label={t('conversation')}>
        {items.length === 0 && pending === null && (
          <p className="text-muted-foreground text-center">{t('turnList.empty')}</p>
        )}
        {items.length > 0 && (
          <ol className="space-y-6">
            {items.map((turn) => (
              <TurnBlock key={turn.turn} turn={turn} onShowTrace={onShowTrace} />
            ))}
          </ol>
        )}
        {pending !== null && (
          <div className={items.length > 0 ? 'mt-6' : undefined}>
            <PendingTurn text={pending} />
          </div>
        )}
      </div>
    </div>
  )
}

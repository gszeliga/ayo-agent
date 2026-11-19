import { ErrorState } from '@/components/StateMessage'
import { LoadError } from '@/components/LoadError'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import type { useCaseTurns } from './queries'
import { TurnBlock } from './TurnBlock'

/** The conversation, oldest first, with "Load earlier turns" above it. */
export function TurnList({ turns }: { turns: ReturnType<typeof useCaseTurns> }) {
  if (turns.isPending) {
    return (
      <div className="space-y-4" aria-label="Loading conversation">
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
        {turns.isFetchPreviousPageError ? (
          <ErrorState
            message="Earlier turns could not be loaded."
            onRetry={() => {
              void turns.fetchPreviousPage()
            }}
          />
        ) : turns.hasPreviousPage ? (
          <Button
            variant="outline"
            disabled={turns.isFetchingPreviousPage}
            onClick={() => {
              void turns.fetchPreviousPage()
            }}
          >
            {turns.isFetchingPreviousPage ? 'Loading…' : 'Load earlier turns'}
          </Button>
        ) : (
          <p className="text-muted-foreground text-xs">Start of the conversation</p>
        )}
      </div>
      <div role="log" aria-live="polite" aria-label="Conversation">
        {items.length === 0 ? (
          <p className="text-muted-foreground text-center">No messages yet.</p>
        ) : (
          <ol className="space-y-6">
            {items.map((turn) => (
              <TurnBlock key={turn.turn} turn={turn} />
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

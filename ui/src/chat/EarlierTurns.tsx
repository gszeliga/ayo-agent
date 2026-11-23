import { ErrorState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'

import type { useCaseTurns } from './queries'

/**
 * Above the loaded turns: "Load earlier turns", its error with Retry, or the start of the
 * conversation. The chat and the Trace tab share it, and the pages it loads.
 */
export function EarlierTurns({ turns }: { turns: ReturnType<typeof useCaseTurns> }) {
  if (turns.isFetchPreviousPageError) {
    return (
      <ErrorState
        message="Earlier turns could not be loaded."
        onRetry={() => {
          void turns.fetchPreviousPage()
        }}
      />
    )
  }
  if (turns.hasPreviousPage) {
    return (
      <Button
        variant="outline"
        disabled={turns.isFetchingPreviousPage}
        onClick={() => {
          void turns.fetchPreviousPage()
        }}
      >
        {turns.isFetchingPreviousPage ? 'Loading…' : 'Load earlier turns'}
      </Button>
    )
  }
  return <p className="text-muted-foreground text-xs">Start of the conversation</p>
}

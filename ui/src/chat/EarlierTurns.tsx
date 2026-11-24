import { useTranslation } from 'react-i18next'

import { ErrorState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'

import type { useCaseTurns } from './queries'

/**
 * Above the loaded turns: "Load earlier turns", its error with Retry, or the start of the
 * conversation. The chat and the Trace tab share it, and the pages it loads.
 */
export function EarlierTurns({ turns }: { turns: ReturnType<typeof useCaseTurns> }) {
  const { t } = useTranslation('chat')
  if (turns.isFetchPreviousPageError) {
    return (
      <ErrorState
        message={t('earlier.failed')}
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
        {turns.isFetchingPreviousPage ? t('earlier.loading') : t('earlier.load')}
      </Button>
    )
  }
  return <p className="text-muted-foreground text-xs">{t('earlier.start')}</p>
}

import { describeError } from '@/api/errors'
import { useConnection } from '@/connection/context'
import { useLanguage } from '@/layout/languageContext'

import { ErrorState } from './StateMessage'

/** A failed query, worded for the user, with Retry. */
export function LoadError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const { connection } = useConnection()
  const { language } = useLanguage()
  return (
    <ErrorState
      message={describeError(error, connection?.baseUrl ?? '', language)}
      onRetry={onRetry}
    />
  )
}

import { describeError } from '@/api/errors'
import { useConnection } from '@/connection/context'

import { ErrorState } from './StateMessage'

/** A failed query, worded for the user, with Retry. */
export function LoadError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const { connection } = useConnection()
  return <ErrorState message={describeError(error, connection?.baseUrl ?? '')} onRetry={onRetry} />
}

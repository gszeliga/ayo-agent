import { describeError } from '@/api/errors'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useConnection } from '@/connection/context'

/** An error inside one part of the page, with Retry. */
export function TabError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const { connection } = useConnection()
  return (
    <Alert variant="destructive" role="alert">
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>{describeError(error, connection?.baseUrl ?? '')}</span>
        <Button variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  )
}

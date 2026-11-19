import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

import { describeSendError } from './sendErrors'

interface Props {
  error: Error
  onSendAgain: () => void
  onReload?: () => void
}

/** A failed send, above the input that has the text back. */
export function SendError({ error, onSendAgain, onReload }: Props) {
  const { message, action } = describeSendError(error)
  return (
    <Alert variant="destructive" role="alert">
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>{message}</span>
        {action === 'send-again' && (
          <Button variant="outline" onClick={onSendAgain}>
            Send again
          </Button>
        )}
        {action === 'reload' && onReload && (
          <Button variant="outline" onClick={onReload}>
            Reload case
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

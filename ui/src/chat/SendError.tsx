import { useTranslation } from 'react-i18next'

import { describeError } from '@/api/errors'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/layout/languageContext'

import { describeSendError } from './sendErrors'

interface Props {
  error: Error
  onSendAgain: () => void
  onReload?: () => void
}

/** A failed send, above the input that has the text back. */
export function SendError({ error, onSendAgain, onReload }: Props) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  const { problem, action } = describeSendError(error)
  const message =
    problem.code === 'refused'
      ? t('sendError.refused', { message: problem.message })
      : problem.code === 'other'
        ? // Not a network error (that is `unreachable`), so the address is never used.
          describeError(problem.error, '', language)
        : t(`sendError.${problem.code}`)
  return (
    <Alert variant="destructive" role="alert">
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>{message}</span>
        {action === 'send-again' && (
          <Button variant="outline" onClick={onSendAgain}>
            {t('sendError.sendAgain')}
          </Button>
        )}
        {action === 'reload' && onReload && (
          <Button variant="outline" onClick={onReload}>
            {t('sendError.reload')}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

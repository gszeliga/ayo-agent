import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { unwrap } from '@/api/client'
import { ApiError, describeError } from '@/api/errors'
import type { components } from '@/api/schema'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useApiClient, useConnection } from '@/connection/context'
import { useLanguage } from '@/layout/languageContext'
import { ROUTES } from '@/paths'

import { caseKey, caseTurnsKey } from './queries'

type CaseDetail = components['schemas']['CaseDetail']

interface Props {
  detail: CaseDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Deletes the case for good (`DELETE /admin/cases/{case_id}`), after saying what goes with
 * it. A 404 counts as done: the case is gone either way. Then back to `/chat`, the case's
 * caches dropped and the list read again.
 */
export function DeleteCaseDialog({ detail, open, onOpenChange }: Props) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  const client = useApiClient()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { connection } = useConnection()
  // Kept as the error and worded when shown, so a language switch rewords it.
  const [error, setError] = useState<Error | null>(null)
  const caseId = detail.case_id
  const remove = useMutation({
    mutationFn: () =>
      unwrap(client.DELETE('/admin/cases/{case_id}', { params: { path: { case_id: caseId } } })),
    retry: false,
  })
  const busy = remove.isPending

  function done(message: string) {
    toast.success(message)
    // Leave first, so the view never reads the case again; then drop what it cached.
    void navigate(ROUTES.chat)
    queryClient.removeQueries({ queryKey: caseKey(caseId) })
    queryClient.removeQueries({ queryKey: caseTurnsKey(caseId) })
    void queryClient.invalidateQueries({ queryKey: ['cases'] })
  }

  function confirm() {
    setError(null)
    remove.mutate(undefined, {
      onSuccess: () => {
        done(t('deleteCase.done'))
      },
      onError: (failure) => {
        if (failure instanceof ApiError && failure.status === 404) {
          done(t('deleteCase.alreadyGone'))
          return
        }
        setError(failure)
      },
    })
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return
        onOpenChange(next)
        setError(null)
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('deleteCase.title')}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                {t(detail.summary ? 'deleteCase.whatWithSummary' : 'deleteCase.what', {
                  turns: t('turns', { count: detail.turns }),
                  annotations: t('deleteCase.annotations', { count: detail.events.length }),
                  actions: t('deleteCase.actions', { count: detail.actions.length }),
                })}
              </p>
              {detail.web_session_id !== null && <p>{t('deleteCase.newCase')}</p>}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>
              {describeError(error, connection?.baseUrl ?? '', language)}
            </AlertDescription>
          </Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t('deleteCase.cancel')}</AlertDialogCancel>
          {/* Not AlertDialogAction: that closes at once; this waits for the answer. */}
          <Button variant="destructive" disabled={busy} onClick={confirm}>
            {busy ? t('deleteCase.deleting') : t('deleteCase.confirm')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

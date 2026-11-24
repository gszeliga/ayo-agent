import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { describeError } from '@/api/errors'
import { ConfirmByTyping } from '@/components/ConfirmByTyping'
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
import { useConnection } from '@/connection/context'
import { i18n } from '@/i18n'
import { useLanguage } from '@/layout/languageContext'
import type { Language } from '@/lib/language'

import { PartialBulkDeleteError, useBulkDelete, type BulkDeleteResult } from './mutations'
import type { Selected } from './useSelection'

const LISTED = 5

function outcome(result: BulkDeleteResult, language: Language): string {
  const t = i18n.getFixedT(language, 'documents')
  const gone = result.notFound.length
  const deleted = t('bulkDelete.deleted', { count: result.deleted.length })
  if (gone === 0) return deleted
  return t('bulkDelete.withGone', { deleted, gone: t('bulkDelete.gone', { count: gone }) })
}

/** Deletes the selection, confirmed by typing `delete N` (in the UI's language). */
export function BulkDeleteDialog({
  selected,
  open,
  onOpenChange,
  onDeleted,
}: {
  selected: Map<string, Selected>
  open: boolean
  onOpenChange: (open: boolean) => void
  /** These ids are gone (deleted, or not found): drop them from the selection. */
  onDeleted: (docIds: string[]) => void
}) {
  const { t } = useTranslation('documents')
  const { language } = useLanguage()
  const [typed, setTyped] = useState('')
  // The failure itself, worded when shown: a language switch rewords it.
  const [error, setError] = useState<Error | null>(null)
  const bulk = useBulkDelete()
  const { connection } = useConnection()
  const baseUrl = connection?.baseUrl ?? ''
  const busy = bulk.isPending
  const entries = [...selected.entries()]
  const expected = t('bulkDelete.phrase', { n: entries.length })
  const chunks = entries.reduce((sum, [, item]) => sum + item.chunks, 0)

  function confirm() {
    bulk.mutate(
      entries.map(([docId]) => docId),
      {
        onSuccess: (result) => {
          toast.success(outcome(result, language))
          onDeleted([...result.deleted.map((d) => d.doc_id), ...result.notFound])
          onOpenChange(false)
        },
        onError: (failure) => {
          if (failure instanceof PartialBulkDeleteError) {
            onDeleted([...failure.done.deleted.map((d) => d.doc_id), ...failure.done.notFound])
          }
          setError(failure)
        },
      },
    )
  }

  const message =
    error === null
      ? null
      : error instanceof PartialBulkDeleteError
        ? t('bulkDelete.partial', {
            outcome: outcome(error.done, language),
            error: describeError(error.cause as Error, baseUrl, language),
          })
        : describeError(error, baseUrl, language)

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return
        onOpenChange(next)
        setTyped('')
        setError(null)
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('bulkDelete.title', { count: entries.length })}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('bulkDelete.warning', { chunks: t('bulkDelete.chunks', { count: chunks }) })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ul
          aria-label={t('bulkDelete.listLabel')}
          className="list-disc space-y-0.5 pl-5 text-[13px]"
        >
          {entries.slice(0, LISTED).map(([docId, item]) => (
            <li key={docId} className="break-words">
              {item.title}
            </li>
          ))}
          {entries.length > LISTED && (
            <li className="text-muted-foreground list-none">
              {t('bulkDelete.more', { n: entries.length - LISTED })}
            </li>
          )}
        </ul>
        <ConfirmByTyping expected={expected} value={typed} onChange={setTyped} disabled={busy} />
        {message !== null && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t('bulkDelete.cancel')}</AlertDialogCancel>
          <Button variant="destructive" disabled={busy || typed !== expected} onClick={confirm}>
            {busy ? t('bulkDelete.deleting') : t('bulkDelete.delete')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { ApiError, describeError } from '@/api/errors'
import type { components } from '@/api/schema'
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
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useConnection } from '@/connection/context'
import { useDelete } from '@/documents/mutations'
import { useLanguage } from '@/layout/languageContext'

type Document = components['schemas']['Document']

/** Delete, confirmed by typing the title (the source key when there is none). */
export function DeleteDialog({ doc, back }: { doc: Document; back: string }) {
  const { t } = useTranslation('document')
  const { language } = useLanguage()
  const name = doc.title ?? doc.source_key
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  // The failure itself, worded when shown: a language switch rewords it.
  const [error, setError] = useState<Error | null>(null)
  const remove = useDelete(doc.doc_id)
  const navigate = useNavigate()
  const { connection } = useConnection()
  const busy = remove.isPending

  function confirm() {
    remove.mutate(undefined, {
      onSuccess: () => {
        toast.success(t('delete.done', { name }))
        void navigate(back)
      },
      onError: (failure) => {
        if (failure instanceof ApiError && failure.status === 404) {
          toast.success(t('delete.alreadyGone', { name }))
          void navigate(back)
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
        setOpen(next)
        setTyped('')
        setError(null)
      }}
    >
      <AlertDialogTrigger asChild>
        <Button variant="outline" className="text-destructive">
          <Trash2 aria-hidden="true" />
          {t('delete.button')}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('delete.title', { name })}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('delete.warning', { count: doc.chunk_count })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ConfirmByTyping expected={name} value={typed} onChange={setTyped} disabled={busy} />
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>
              {describeError(error, connection?.baseUrl ?? '', language)}
            </AlertDescription>
          </Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t('delete.cancel')}</AlertDialogCancel>
          {/* Not AlertDialogAction: that closes at once; this waits for the answer. */}
          <Button variant="destructive" disabled={busy || typed !== name} onClick={confirm}>
            {busy ? t('delete.deleting') : t('delete.button')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

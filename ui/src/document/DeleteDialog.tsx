import { Trash2 } from 'lucide-react'
import { useState } from 'react'
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

type Document = components['schemas']['Document']

/** Delete, confirmed by typing the title (the source key when there is none). */
export function DeleteDialog({ doc, back }: { doc: Document; back: string }) {
  const name = doc.title ?? doc.source_key
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)
  const remove = useDelete(doc.doc_id)
  const navigate = useNavigate()
  const { connection } = useConnection()
  const busy = remove.isPending

  function confirm() {
    remove.mutate(undefined, {
      onSuccess: () => {
        toast.success(`Deleted ${name}`)
        void navigate(back)
      },
      onError: (failure) => {
        if (failure instanceof ApiError && failure.status === 404) {
          toast.success(`${name} was already deleted`)
          void navigate(back)
          return
        }
        setError(describeError(failure, connection?.baseUrl ?? ''))
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
          Delete
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {name}?</AlertDialogTitle>
          <AlertDialogDescription>
            The document and its {doc.chunk_count} chunks are removed for good. There is no undo.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ConfirmByTyping expected={name} value={typed} onChange={setTyped} disabled={busy} />
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          {/* Not AlertDialogAction: that closes at once; this waits for the answer. */}
          <Button variant="destructive" disabled={busy || typed !== name} onClick={confirm}>
            {busy ? 'Deleting…' : 'Delete'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

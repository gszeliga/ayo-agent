import { useState } from 'react'
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

import { PartialBulkDeleteError, useBulkDelete, type BulkDeleteResult } from './mutations'
import type { Selected } from './useSelection'

const LISTED = 5

const plural = (n: number, one: string, many: string) => `${String(n)} ${n === 1 ? one : many}`

function outcome(result: BulkDeleteResult): string {
  const gone = result.notFound.length
  const deleted = `Deleted ${plural(result.deleted.length, 'document', 'documents')}`
  return gone === 0 ? deleted : `${deleted}; ${plural(gone, 'was', 'were')} already gone`
}

/** Deletes the selection, confirmed by typing `delete N`. */
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
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)
  const bulk = useBulkDelete()
  const { connection } = useConnection()
  const busy = bulk.isPending
  const entries = [...selected.entries()]
  const expected = `delete ${String(entries.length)}`
  const chunks = entries.reduce((sum, [, item]) => sum + item.chunks, 0)

  function confirm() {
    bulk.mutate(
      entries.map(([docId]) => docId),
      {
        onSuccess: (result) => {
          toast.success(outcome(result))
          onDeleted([...result.deleted.map((d) => d.doc_id), ...result.notFound])
          onOpenChange(false)
        },
        onError: (failure) => {
          if (failure instanceof PartialBulkDeleteError) {
            onDeleted([...failure.done.deleted.map((d) => d.doc_id), ...failure.done.notFound])
            setError(
              `${outcome(failure.done)}, then it stopped: ${describeError(
                failure.cause as Error,
                connection?.baseUrl ?? '',
              )} The rest are still selected.`,
            )
          } else {
            setError(describeError(failure, connection?.baseUrl ?? ''))
          }
        },
      },
    )
  }

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
          <AlertDialogTitle>
            Delete {plural(entries.length, 'document', 'documents')}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            They and their {plural(chunks, 'chunk', 'chunks')} are removed for good. There is no
            undo.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ul aria-label="Documents to delete" className="list-disc space-y-0.5 pl-5 text-[13px]">
          {entries.slice(0, LISTED).map(([docId, item]) => (
            <li key={docId} className="break-words">
              {item.title}
            </li>
          ))}
          {entries.length > LISTED && (
            <li className="text-muted-foreground list-none">and {entries.length - LISTED} more</li>
          )}
        </ul>
        <ConfirmByTyping expected={expected} value={typed} onChange={setTyped} disabled={busy} />
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <Button variant="destructive" disabled={busy || typed !== expected} onClick={confirm}>
            {busy ? 'Deleting…' : 'Delete'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

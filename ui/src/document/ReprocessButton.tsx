import { ChevronDown, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { ApiError, describeError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useConnection } from '@/connection/context'
import { useReprocess } from '@/documents/mutations'

export const DOCUMENT_CHANGED =
  'A newer upload replaced it while reprocessing; nothing was written.'
export const REPROCESS_PROVIDER_FAILED = 'The embedding provider failed; nothing was written.'

/** Reprocess (skipped when up to date), with Force in the menu. */
export function ReprocessButton({ docId, onGone }: { docId: string; onGone: () => void }) {
  const reprocess = useReprocess(docId)
  const { connection } = useConnection()

  function run(force: boolean) {
    reprocess.mutate(force, {
      onSuccess: (result) => {
        if (result.status === 'up_to_date') {
          toast.success('Already up to date: nothing to do.', {
            description: 'Use Force reprocess to rebuild it anyway.',
          })
        } else {
          toast.success(`Reprocessed: ${String(result.chunk_count ?? 0)} chunks`)
        }
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 404) {
          onGone()
        } else if (error instanceof ApiError && error.status === 409) {
          toast.error(DOCUMENT_CHANGED, {
            action: {
              label: 'Retry',
              onClick: () => {
                run(force)
              },
            },
          })
        } else if (error instanceof ApiError && error.status === 502) {
          toast.error(REPROCESS_PROVIDER_FAILED)
        } else {
          toast.error(describeError(error, connection?.baseUrl ?? ''))
        }
      },
    })
  }

  const busy = reprocess.isPending
  return (
    <div className="flex">
      <Button
        variant="outline"
        className="rounded-r-none"
        disabled={busy}
        onClick={() => {
          run(false)
        }}
      >
        <RefreshCw aria-hidden="true" className={busy ? 'animate-spin' : undefined} />
        {busy ? 'Reprocessing…' : 'Reprocess'}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            className="-ml-px rounded-l-none"
            disabled={busy}
            aria-label="More reprocess options"
          >
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuItem
            onSelect={() => {
              run(true)
            }}
          >
            <div>
              <div className="font-medium">Force reprocess</div>
              <div className="text-muted-foreground text-xs">
                Re-chunk and re-embed even if up to date.
              </div>
            </div>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

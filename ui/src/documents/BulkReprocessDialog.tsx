import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { unwrap } from '@/api/client'
import { ApiError, describeError } from '@/api/errors'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useApiClient, useConnection } from '@/connection/context'
import { REPROCESS_PROVIDER_FAILED } from '@/document/ReprocessButton'

import {
  emptyCounts,
  OUTCOME_LABELS,
  OUTCOMES,
  runBulkReprocess,
  type Outcome,
  type Progress,
  type RunResult,
  type Target,
} from './bulkReprocess'
import type { ListParams } from './listParams'
import { refreshLists } from './mutations'
import { fetchAllMatching } from './queries'
import type { Selected } from './useSelection'

/** What to reprocess: the selection, or every document matching the list's filters. */
export type ReprocessSource =
  | { kind: 'selection'; items: Map<string, Selected> }
  | { kind: 'filter'; params: ListParams; total: number }

type Stage =
  | { name: 'confirm' }
  | { name: 'collecting' }
  | { name: 'running'; progress: Progress }
  | { name: 'done'; result: RunResult }

/** Outcomes that are settled: these documents leave the selection; the others stay. */
const SETTLED: readonly Outcome[] = ['reprocessed', 'up_to_date', 'gone']

const settledCount = (result: RunResult) =>
  SETTLED.reduce((sum, outcome) => sum + result.counts[outcome], 0)

const plural = (n: number, one: string, many: string) => `${String(n)} ${n === 1 ? one : many}`

function ProgressBar({ done, total }: { done: number; total: number }) {
  const share = total === 0 ? 100 : (done / total) * 100
  return (
    <div
      role="progressbar"
      aria-label="Reprocess progress"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
      className="bg-secondary h-2 overflow-hidden rounded-full"
    >
      <div
        className="bg-primary h-full transition-[width]"
        style={{ width: `${String(share)}%` }}
      />
    </div>
  )
}

function Summary({ result, failure }: { result: RunResult; failure: string | null }) {
  const rows = OUTCOMES.filter((outcome) => result.counts[outcome] > 0)
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Outcome">
        <dl className="space-y-1.5">
          {rows.map((outcome) => (
            <div key={outcome} className="flex justify-between gap-4">
              <dt>{OUTCOME_LABELS[outcome]}</dt>
              <dd className="tabular-nums">{result.counts[outcome]}</dd>
            </div>
          ))}
          {result.notStarted > 0 && (
            <div className="text-muted-foreground flex justify-between gap-4">
              <dt>Not started</dt>
              <dd className="tabular-nums">{result.notStarted}</dd>
            </div>
          )}
        </dl>
      </div>
      {failure && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{failure}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

/**
 * Reprocesses many documents, one call at a time, with progress and a stop between
 * documents. Lists and counts are refreshed once, at the end.
 */
export function BulkReprocessDialog({
  source,
  open,
  onOpenChange,
  onFinished,
}: {
  source: ReprocessSource
  open: boolean
  onOpenChange: (open: boolean) => void
  /** These documents are settled (reprocessed, up to date or gone): drop them from the selection. */
  onFinished?: (docIds: string[]) => void
}) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const { connection } = useConnection()
  const [stage, setStage] = useState<Stage>({ name: 'confirm' })
  const [error, setError] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)
  const stop = useRef(false)
  const mounted = useRef(true)
  const busy = stage.name === 'collecting' || stage.name === 'running'
  const baseUrl = connection?.baseUrl ?? ''

  // Leaving the page ends the run after the current document.
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      stop.current = true
    }
  }, [])

  // Closing or reloading the tab mid-run asks first.
  useEffect(() => {
    if (!busy) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
    }
  }, [busy])

  const count = source.kind === 'selection' ? source.items.size : source.total

  function describe(failure: Error): string {
    if (failure instanceof ApiError && failure.status === 502) return REPROCESS_PROVIDER_FAILED
    return describeError(failure, baseUrl)
  }

  async function start() {
    setError(null)
    setStopping(false)
    stop.current = false
    let targets: Target[]
    if (source.kind === 'selection') {
      targets = [...source.items].map(([docId, item]) => ({ docId, title: item.title }))
    } else {
      setStage({ name: 'collecting' })
      try {
        targets = await fetchAllMatching(client, source.params)
      } catch (failure) {
        if (!mounted.current) return
        setStage({ name: 'confirm' })
        setError(describe(failure as Error))
        return
      }
      // The page was left while the ids were being collected.
      if (!mounted.current) return
    }

    setStage({
      name: 'running',
      progress: { done: 0, total: targets.length, current: null, counts: emptyCounts() },
    })
    const result = await runBulkReprocess(
      targets,
      (docId) =>
        unwrap(
          client.POST('/admin/documents/{doc_id}/reprocess', {
            params: { path: { doc_id: docId }, query: { force: false } },
          }),
        ),
      {
        shouldStop: () => stop.current,
        onProgress: (progress) => {
          if (mounted.current) setStage({ name: 'running', progress })
        },
      },
    )

    for (const [docId, outcome] of result.outcomes) {
      if (outcome === 'reprocessed') {
        void queryClient.invalidateQueries({ queryKey: ['document', docId] })
      } else if (outcome === 'gone') {
        queryClient.removeQueries({ queryKey: ['document', docId] })
      }
    }
    void refreshLists(queryClient)
    if (!mounted.current) return
    setStage({ name: 'done', result })
    onFinished?.(
      [...result.outcomes].filter(([, outcome]) => SETTLED.includes(outcome)).map(([id]) => id),
    )
  }

  function close(next: boolean) {
    if (busy) return
    onOpenChange(next)
    if (!next) {
      setStage({ name: 'confirm' })
      setError(null)
    }
  }

  const result = stage.name === 'done' ? stage.result : null
  const failure =
    result?.stopped?.by === 'error'
      ? `Stopped at “${result.stopped.target.title}”: ${describe(result.stopped.error)}`
      : null

  return (
    <AlertDialog open={open} onOpenChange={close}>
      <AlertDialogContent>
        {stage.name === 'confirm' || stage.name === 'collecting' ? (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>
                Reprocess {plural(count, 'document', 'documents')}?
              </AlertDialogTitle>
              <AlertDialogDescription>
                {source.kind === 'filter'
                  ? 'Every document matching the current filters is'
                  : 'Each one is'}{' '}
                re-chunked and re-embedded with the current settings, one at a time, calling the
                embedding provider for each. Documents already up to date are skipped. Keep this tab
                open until it finishes.
              </AlertDialogDescription>
            </AlertDialogHeader>
            {error && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <AlertDialogFooter>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  close(false)
                }}
              >
                Cancel
              </Button>
              <Button disabled={busy} onClick={() => void start()}>
                {busy ? 'Finding documents…' : 'Start'}
              </Button>
            </AlertDialogFooter>
          </>
        ) : stage.name === 'running' ? (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>Reprocessing documents</AlertDialogTitle>
              <AlertDialogDescription>
                {stage.progress.done} of {stage.progress.total} done. Keep this tab open.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <ProgressBar done={stage.progress.done} total={stage.progress.total} />
            <p aria-live="polite" className="text-muted-foreground truncate text-[13px]">
              {stopping
                ? 'Stopping after this document…'
                : stage.progress.current
                  ? `Now: ${stage.progress.current.title}`
                  : ''}
            </p>
            <AlertDialogFooter>
              <Button
                variant="outline"
                disabled={stopping}
                onClick={() => {
                  stop.current = true
                  setStopping(true)
                }}
              >
                Stop
              </Button>
            </AlertDialogFooter>
          </>
        ) : (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {stage.result.stopped ? 'Reprocess stopped' : 'Reprocess finished'}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {stage.result.stopped?.by === 'user' ? 'Stopped at your request. ' : ''}
                {plural(stage.result.outcomes.size, 'document', 'documents')} processed.
                {source.kind === 'selection' &&
                stage.result.outcomes.size - settledCount(stage.result) + stage.result.notStarted >
                  0
                  ? ' The ones not settled are still selected.'
                  : ''}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <Summary result={stage.result} failure={failure} />
            <AlertDialogFooter>
              <Button
                onClick={() => {
                  close(false)
                }}
              >
                Close
              </Button>
            </AlertDialogFooter>
          </>
        )}
      </AlertDialogContent>
    </AlertDialog>
  )
}

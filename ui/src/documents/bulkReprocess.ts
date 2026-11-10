import { ApiError } from '@/api/errors'

/** A document to reprocess: its id, and what to call it on screen. */
export interface Target {
  docId: string
  title: string
}

/** How one document ended. `failed` stops the run: the error would hit the rest too. */
export type Outcome = 'reprocessed' | 'up_to_date' | 'changed' | 'gone' | 'failed'

export const OUTCOMES: readonly Outcome[] = [
  'reprocessed',
  'up_to_date',
  'changed',
  'gone',
  'failed',
]

/** Each outcome in words, as the summary lists it. */
export const OUTCOME_LABELS: Record<Outcome, string> = {
  reprocessed: 'Reprocessed',
  up_to_date: 'Already up to date',
  changed: 'Replaced by a newer upload meanwhile',
  gone: 'Deleted meanwhile',
  failed: 'Failed',
}

export type Counts = Record<Outcome, number>

export interface Progress {
  /** Documents finished, whatever their outcome. */
  done: number
  total: number
  /** The document being reprocessed; null between documents and at the end. */
  current: Target | null
  counts: Counts
}

export interface RunResult {
  counts: Counts
  /** Each finished document's outcome, in the order they ran. */
  outcomes: Map<string, Outcome>
  /** Null when every document ran; else who stopped it (the error for `failed`). */
  stopped: null | { by: 'user' } | { by: 'error'; error: Error; target: Target }
  /** Documents never started (after a stop). */
  notStarted: number
}

/** The API's answer to one reprocess (`force` off: an up-to-date one is skipped). */
export type ReprocessOne = (docId: string) => Promise<{ status: 'indexed' | 'up_to_date' }>

export const emptyCounts = (): Counts => ({
  reprocessed: 0,
  up_to_date: 0,
  changed: 0,
  gone: 0,
  failed: 0,
})

/**
 * The outcome of an error that concerns this document only (`404` deleted meanwhile, `409`
 * replaced meanwhile); null for one that would hit every document (provider down, network,
 * auth, anything unexpected).
 */
function documentOnly(error: unknown): Outcome | null {
  if (!(error instanceof ApiError)) return null
  if (error.status === 404) return 'gone'
  if (error.status === 409) return 'changed'
  return null
}

/**
 * Reprocesses the targets one after the other. `shouldStop` is asked before each document,
 * so a stop takes effect between them: a reprocess already sent is never cut short (the
 * server would finish it anyway). Never rejects: a failure is in the result.
 */
export async function runBulkReprocess(
  targets: readonly Target[],
  reprocess: ReprocessOne,
  {
    shouldStop = () => false,
    onProgress = () => undefined,
  }: { shouldStop?: () => boolean; onProgress?: (progress: Progress) => void } = {},
): Promise<RunResult> {
  const counts = emptyCounts()
  const outcomes = new Map<string, Outcome>()
  const report = (current: Target | null) => {
    onProgress({ done: outcomes.size, total: targets.length, current, counts: { ...counts } })
  }
  const finish = (stopped: RunResult['stopped']): RunResult => {
    report(null)
    return {
      counts: { ...counts },
      outcomes,
      stopped,
      notStarted: targets.length - outcomes.size,
    }
  }

  for (const target of targets) {
    if (shouldStop()) return finish({ by: 'user' })
    report(target)
    let outcome: Outcome
    try {
      const result = await reprocess(target.docId)
      outcome = result.status === 'indexed' ? 'reprocessed' : 'up_to_date'
    } catch (error) {
      const own = documentOnly(error)
      if (own === null) {
        counts.failed += 1
        outcomes.set(target.docId, 'failed')
        const failure = error instanceof Error ? error : new Error(String(error))
        return finish({ by: 'error', error: failure, target })
      }
      outcome = own
    }
    counts[outcome] += 1
    outcomes.set(target.docId, outcome)
  }
  return finish(null)
}

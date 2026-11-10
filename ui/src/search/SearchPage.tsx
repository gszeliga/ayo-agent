import { AlertTriangle, Search } from 'lucide-react'
import { useId, useState, type KeyboardEvent, type SubmitEvent } from 'react'
import { Link, useSearchParams } from 'react-router'

import { ApiError, describeError } from '@/api/errors'
import { EmptyState, ErrorState } from '@/components/StateMessage'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useConnection } from '@/connection/context'
import { DEFAULT_PARAMS, toSearchParams as toListSearch } from '@/documents/listParams'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/paths'
import { useCachedServiceHealth } from '@/settings/healthQuery'

import { ResultCard } from './ResultCard'
import {
  charCount,
  parseMinSimilarity,
  parseSearchOptions,
  parseTopK,
  QUERY_MAX_CHARS,
  toRequest,
  toSearchParams,
  type SearchOptions,
} from './searchParams'
import { SearchOptionsPopover } from './SearchOptionsPopover'
import { SearchSummary } from './SearchSummary'
import { TenantPicker } from './TenantPicker'
import { useLastSearch, useSearch, type LastSearch } from './useSearch'

const OUTDATED_LIST = `${ROUTES.documents}?${toListSearch({ ...DEFAULT_PARAMS, status: 'outdated' }).toString()}`

interface Problems {
  query?: string
  top_k?: string
  min_similarity?: string
  other?: string
}

/** The form as typed: options start from the URL, the question from the last search. */
interface Draft {
  question: string
  tenants: string[]
  topK: string
  minSimilarity: string
  includeOutdated: boolean
}

function draftFrom(options: SearchOptions, question: string): Draft {
  return {
    question,
    tenants: options.tenants,
    topK: String(options.topK),
    minSimilarity: options.minSimilarity === null ? '' : String(options.minSimilarity),
    includeOutdated: options.includeOutdated,
  }
}

/** The draft checked as the API would; the options to search with, or what is wrong. */
function validate(draft: Draft): { options: SearchOptions } | { problems: Problems } {
  const problems: Problems = {}
  const length = charCount(draft.question.trim())
  if (length === 0) problems.query = 'Type a question.'
  else if (length > QUERY_MAX_CHARS) {
    problems.query = `At most ${String(QUERY_MAX_CHARS)} characters (now ${String(length)}).`
  }
  const topK = parseTopK(draft.topK)
  if (topK === null) problems.top_k = 'A whole number from 1 to 50.'
  const min = draft.minSimilarity.trim() ? parseMinSimilarity(draft.minSimilarity) : null
  if (draft.minSimilarity.trim() && min === null) {
    problems.min_similarity = 'A number from 0 to 1, or empty for none.'
  }
  if (Object.keys(problems).length > 0 || topK === null) return { problems }
  return {
    options: {
      tenants: draft.tenants,
      topK,
      minSimilarity: min,
      includeOutdated: draft.includeOutdated,
    },
  }
}

/** A failed search, worded for the user; a 422 goes next to its fields instead. */
function problemsFrom(error: Error, baseUrl: string): Problems {
  if (error instanceof ApiError && error.status === 422) {
    const fields = error.fieldErrors()
    const placed: Problems = {}
    for (const key of ['query', 'top_k', 'min_similarity'] as const) {
      if (fields[key]) placed[key] = fields[key]
    }
    if (Object.keys(placed).length > 0) return placed
  }
  if (error instanceof ApiError && error.status === 502) {
    return {
      other:
        'The embedding provider failed: the question could not be embedded, so nothing was' +
        ' searched. Try again in a moment.',
    }
  }
  return { other: describeError(error, baseUrl) }
}

export function SearchPage() {
  useDocumentTitle('Test search')
  const { connection } = useConnection()
  const [searchParams, setSearchParams] = useSearchParams()
  const last = useLastSearch()
  const search = useSearch()
  const embeddings = useCachedServiceHealth()?.embeddings
  const [draft, setDraft] = useState<Draft>(() =>
    draftFrom(parseSearchOptions(searchParams), last?.question ?? ''),
  )
  const [checked, setChecked] = useState<Problems>({})
  const [optionsOpen, setOptionsOpen] = useState(false)
  const questionId = useId()
  const questionNoteId = useId()
  const topKId = useId()

  const failed = search.error ? problemsFrom(search.error, connection?.baseUrl ?? '') : {}
  const problems: Problems = { ...failed, ...checked }
  const shown: LastSearch | null = search.isError ? null : last

  function run(changes: Partial<Draft> = {}) {
    if (search.isPending) return
    const next = { ...draft, ...changes }
    setDraft(next)
    const result = validate(next)
    if ('problems' in result) {
      setChecked(result.problems)
      if (result.problems.min_similarity) setOptionsOpen(true)
      return
    }
    setChecked({})
    setOptionsOpen(false)
    const question = next.question.trim()
    // The options searched with go in the URL (a reload keeps them); the question never.
    setSearchParams(toSearchParams(result.options), { replace: true })
    search.mutate({
      question,
      options: result.options,
      request: toRequest(question, result.options),
    })
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    run()
  }

  function onQuestionKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter searches; Shift+Enter (or composing an accent) types as usual.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      run()
    }
  }

  /** A change to the form: a failed search's message no longer applies. */
  function edit(changes: Partial<Draft>, clears?: keyof Problems) {
    setDraft({ ...draft, ...changes })
    if (clears) setChecked({ ...checked, [clears]: undefined })
    if (search.isError) search.reset()
  }

  const length = charCount(draft.question.trim())

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-[22px] font-semibold">Test search</h1>
        <p className="text-muted-foreground">
          Ask a question the way a plant team would and see which chunks the copilot would retrieve,
          nearest first.
        </p>
      </div>

      {embeddings?.status === 'down' && (
        <Alert role="note" className="bg-warning-muted text-warning border-transparent">
          <AlertTriangle aria-hidden="true" />
          <AlertDescription className="text-warning">
            The embedding provider is down: every question is embedded first, so searches fail until
            it is back{embeddings.error ? ` (${embeddings.error})` : ''}.
          </AlertDescription>
        </Alert>
      )}

      <form
        noValidate
        aria-label="Search"
        className="bg-card space-y-4 rounded-xl border p-4"
        onSubmit={submit}
      >
        <div className="space-y-1.5">
          <Label htmlFor={questionId}>Question</Label>
          <textarea
            id={questionId}
            rows={3}
            aria-invalid={problems.query ? true : undefined}
            aria-describedby={questionNoteId}
            placeholder="¿Qué hago si la junta de la bomba pierde presión?"
            className={cn(
              'border-input placeholder:text-muted-foreground dark:bg-input/30 block min-h-19 w-full resize-y rounded-md border bg-transparent px-3 py-2 text-base shadow-xs outline-none md:text-sm',
              'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
              'aria-invalid:border-destructive aria-invalid:ring-destructive/20',
            )}
            value={draft.question}
            onChange={(event) => {
              edit({ question: event.target.value }, 'query')
            }}
            onKeyDown={onQuestionKey}
          />
          <div id={questionNoteId} className="flex justify-between gap-3 text-[13px]">
            {problems.query ? (
              <p className="text-destructive">{problems.query}</p>
            ) : (
              <p className="text-muted-foreground">
                Enter searches, Shift+Enter adds a line. Questions are never logged or put in the
                URL.
              </p>
            )}
            <p
              className={cn(
                'tabular-nums whitespace-nowrap',
                length > QUERY_MAX_CHARS ? 'text-destructive' : 'text-muted-foreground',
              )}
            >
              {length} / {QUERY_MAX_CHARS}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <TenantPicker
            value={draft.tenants}
            onChange={(tenants) => {
              edit({ tenants })
            }}
          />
          <div className="space-y-1.5">
            <Label htmlFor={topKId}>Top k</Label>
            <Input
              id={topKId}
              type="number"
              min={1}
              max={50}
              inputMode="numeric"
              className="w-24 tabular-nums"
              aria-invalid={problems.top_k ? true : undefined}
              value={draft.topK}
              onChange={(event) => {
                edit({ topK: event.target.value }, 'top_k')
              }}
            />
          </div>
          <SearchOptionsPopover
            open={optionsOpen}
            onOpenChange={setOptionsOpen}
            minSimilarity={draft.minSimilarity}
            onMinSimilarity={(minSimilarity) => {
              edit({ minSimilarity }, 'min_similarity')
            }}
            minError={problems.min_similarity}
            includeOutdated={draft.includeOutdated}
            onIncludeOutdated={(includeOutdated) => {
              edit({ includeOutdated })
            }}
          />
          <Button type="submit" className="ml-auto min-w-28" disabled={search.isPending}>
            <Search aria-hidden="true" />
            {search.isPending ? 'Searching…' : 'Search'}
          </Button>
        </div>
        {problems.top_k && <p className="text-destructive text-[13px]">Top k: {problems.top_k}</p>}
        {problems.min_similarity && !optionsOpen && (
          <p className="text-destructive text-[13px]">
            Minimum similarity: {problems.min_similarity}
          </p>
        )}
      </form>

      {problems.other && (
        <ErrorState
          message={problems.other}
          onRetry={() => {
            run()
          }}
        />
      )}

      {shown && shown.response.skipped.embedder_mismatch > 0 && (
        <SkippedBanner
          count={shown.response.skipped.embedder_mismatch}
          onInclude={() => {
            run({ question: shown.question, includeOutdated: true })
          }}
        />
      )}

      {shown && <SearchSummary last={shown} />}

      {search.isPending && !shown ? (
        <div aria-busy="true" aria-label="Searching" className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : shown && shown.response.results.length > 0 ? (
        <ol
          aria-label="Results"
          aria-busy={search.isPending}
          className={cn('space-y-2.5', search.isPending && 'opacity-50')}
        >
          {shown.response.results.map((hit) => (
            <ResultCard
              key={hit.chunk_id}
              hit={hit}
              embedderConfig={shown.response.debug?.embedder_config ?? 'the current one'}
            />
          ))}
        </ol>
      ) : shown ? (
        <NoResults
          last={shown}
          onClearMinimum={() => {
            run({ question: shown.question, minSimilarity: '' })
          }}
        />
      ) : (
        !problems.other && (
          <EmptyState
            title="Results appear here"
            description="Each result is a chunk: how close it is to the question (cosine similarity, 1 is the same direction), its document, and where in it the chunk sits. Each search embeds the question once."
          />
        )
      )}
    </div>
  )
}

function SkippedBanner({ count, onInclude }: { count: number; onInclude: () => void }) {
  const one = count === 1
  return (
    <Alert role="status" className="bg-warning-muted text-warning border-transparent">
      <AlertTriangle aria-hidden="true" />
      <AlertDescription className="text-warning flex flex-wrap items-center justify-between gap-3">
        <span className="flex-[1_1_22rem]">
          {one ? '1 document was' : `${String(count)} documents were`} left out:{' '}
          {one ? 'it was' : 'they were'} embedded with a different model (or before models were
          recorded), so {one ? 'its' : 'their'} vectors can’t be compared. Reprocess{' '}
          {one ? 'it' : 'them'} to make {one ? 'it' : 'them'} searchable.
        </span>
        <span className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onInclude}>
            Include them
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to={OUTDATED_LIST}>Review outdated documents</Link>
          </Button>
        </span>
      </AlertDescription>
    </Alert>
  )
}

/**
 * No results. Without a minimum similarity, any searchable chunk would have come back, so
 * nothing was searchable; with one, the API does not say whether anything was searched.
 */
function NoResults({ last, onClearMinimum }: { last: LastSearch; onClearMinimum: () => void }) {
  const { options, response } = last
  if (options.minSimilarity !== null) {
    return (
      <EmptyState
        title="Nothing reached the minimum similarity"
        description={`None of the top ${String(options.topK)} chunks scored ${String(options.minSimilarity)} or more.`}
        action={
          <Button type="button" variant="outline" onClick={onClearMinimum}>
            Clear the minimum and search again
          </Button>
        }
      />
    )
  }
  if (response.skipped.embedder_mismatch > 0) {
    return (
      <EmptyState
        title="No searchable documents"
        description="Every matching document was embedded with another model."
      />
    )
  }
  return (
    <EmptyState
      title="Nothing to search"
      description={
        options.tenants.length > 0
          ? 'These tenants have no documents.'
          : 'The knowledge base is empty: upload a document first.'
      }
    />
  )
}

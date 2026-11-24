import { AlertTriangle, Search } from 'lucide-react'
import { useId, useState, type KeyboardEvent, type SubmitEvent } from 'react'
import { useTranslation } from 'react-i18next'
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
import { i18n } from '@/i18n'
import { useLanguage } from '@/layout/languageContext'
import { formatDecimal } from '@/lib/format'
import type { Language } from '@/lib/language'
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

/** A field's problem, worded when shown (`describeProblem`); `api` is the API's own message. */
type FieldProblem =
  | { code: 'queryEmpty' | 'topK' | 'minSimilarity' }
  | { code: 'queryTooLong'; length: number }
  | { code: 'api'; message: string }

/** A failed search that no field owns. */
type OtherProblem = { code: 'providerFailed' } | { code: 'error'; error: Error }

interface Problems {
  query?: FieldProblem
  top_k?: FieldProblem
  min_similarity?: FieldProblem
  other?: OtherProblem
}

function describeProblem(problem: FieldProblem, language: Language): string {
  const t = i18n.getFixedT(language, 'search')
  switch (problem.code) {
    case 'api':
      return problem.message
    case 'queryTooLong':
      return t('problem.queryTooLong', { max: QUERY_MAX_CHARS, n: problem.length })
    default:
      return t(`problem.${problem.code}`)
  }
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
  if (length === 0) problems.query = { code: 'queryEmpty' }
  else if (length > QUERY_MAX_CHARS) problems.query = { code: 'queryTooLong', length }
  const topK = parseTopK(draft.topK)
  if (topK === null) problems.top_k = { code: 'topK' }
  const min = draft.minSimilarity.trim() ? parseMinSimilarity(draft.minSimilarity) : null
  if (draft.minSimilarity.trim() && min === null) {
    problems.min_similarity = { code: 'minSimilarity' }
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
function problemsFrom(error: Error): Problems {
  if (error instanceof ApiError && error.status === 422) {
    const fields = error.fieldErrors()
    const placed: Problems = {}
    for (const key of ['query', 'top_k', 'min_similarity'] as const) {
      const message = fields[key]
      if (message) placed[key] = { code: 'api', message }
    }
    if (Object.keys(placed).length > 0) return placed
  }
  if (error instanceof ApiError && error.status === 502) {
    return { other: { code: 'providerFailed' } }
  }
  return { other: { code: 'error', error } }
}

export function SearchPage() {
  const { t } = useTranslation('search')
  const { language } = useLanguage()
  useDocumentTitle(t('pageTitle'))
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

  const failed = search.error ? problemsFrom(search.error) : {}
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
  const words = (problem: FieldProblem | undefined) =>
    problem ? describeProblem(problem, language) : undefined
  const other = problems.other
  const otherMessage =
    other === undefined
      ? null
      : other.code === 'providerFailed'
        ? t('problem.providerFailed')
        : describeError(other.error, connection?.baseUrl ?? '', language)

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-[22px] font-semibold">{t('heading')}</h1>
        <p className="text-muted-foreground">{t('intro')}</p>
      </div>

      {embeddings?.status === 'down' && (
        <Alert role="note" className="bg-warning-muted text-warning border-transparent">
          <AlertTriangle aria-hidden="true" />
          <AlertDescription className="text-warning">
            {embeddings.error
              ? t('providerDownWithError', { error: embeddings.error })
              : t('providerDown')}
          </AlertDescription>
        </Alert>
      )}

      <form
        noValidate
        aria-label={t('form.label')}
        className="bg-card space-y-4 rounded-xl border p-4"
        onSubmit={submit}
      >
        <div className="space-y-1.5">
          <Label htmlFor={questionId}>{t('form.question')}</Label>
          <textarea
            id={questionId}
            rows={3}
            aria-invalid={problems.query ? true : undefined}
            aria-describedby={questionNoteId}
            // eslint-disable-next-line i18next/no-literal-string -- an example question in the content's language
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
              <p className="text-destructive">{words(problems.query)}</p>
            ) : (
              <p className="text-muted-foreground">{t('form.hint')}</p>
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
            <Label htmlFor={topKId}>{t('form.topK')}</Label>
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
            minError={words(problems.min_similarity)}
            includeOutdated={draft.includeOutdated}
            onIncludeOutdated={(includeOutdated) => {
              edit({ includeOutdated })
            }}
          />
          <Button type="submit" className="ml-auto min-w-28" disabled={search.isPending}>
            <Search aria-hidden="true" />
            {search.isPending ? t('form.searching') : t('form.submit')}
          </Button>
        </div>
        {problems.top_k && (
          <p className="text-destructive text-[13px]">
            {t('form.topK')}: {words(problems.top_k)}
          </p>
        )}
        {problems.min_similarity && !optionsOpen && (
          <p className="text-destructive text-[13px]">
            {t('options.min')}: {words(problems.min_similarity)}
          </p>
        )}
      </form>

      {otherMessage !== null && (
        <ErrorState
          message={otherMessage}
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
        <div aria-busy="true" aria-label={t('form.loading')} className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : shown && shown.response.results.length > 0 ? (
        <ol
          aria-label={t('form.results')}
          aria-busy={search.isPending}
          className={cn('space-y-2.5', search.isPending && 'opacity-50')}
        >
          {shown.response.results.map((hit) => (
            <ResultCard
              key={hit.chunk_id}
              hit={hit}
              embedderConfig={shown.response.debug?.embedder_config ?? t('result.currentConfig')}
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
          <EmptyState title={t('empty.introTitle')} description={t('empty.introDescription')} />
        )
      )}
    </div>
  )
}

function SkippedBanner({ count, onInclude }: { count: number; onInclude: () => void }) {
  const { t } = useTranslation('search')
  return (
    <Alert role="status" className="bg-warning-muted text-warning border-transparent">
      <AlertTriangle aria-hidden="true" />
      <AlertDescription className="text-warning flex flex-wrap items-center justify-between gap-3">
        <span className="flex-[1_1_22rem]">{t('skipped.text', { count })}</span>
        <span className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onInclude}>
            {t('skipped.include')}
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to={OUTDATED_LIST}>{t('skipped.review')}</Link>
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
  const { t } = useTranslation('search')
  const { language } = useLanguage()
  const { options, response } = last
  if (options.minSimilarity !== null) {
    return (
      <EmptyState
        title={t('empty.minTitle')}
        description={t('empty.minDescription', {
          topK: options.topK,
          min: formatDecimal(options.minSimilarity, language, { min: 0, max: 15 }),
        })}
        action={
          <Button type="button" variant="outline" onClick={onClearMinimum}>
            {t('empty.clearMin')}
          </Button>
        }
      />
    )
  }
  if (response.skipped.embedder_mismatch > 0) {
    return (
      <EmptyState
        title={t('empty.noSearchableTitle')}
        description={t('empty.noSearchableDescription')}
      />
    )
  }
  return (
    <EmptyState
      title={t('empty.nothingTitle')}
      description={options.tenants.length > 0 ? t('empty.nothingTenants') : t('empty.nothingEmpty')}
    />
  )
}

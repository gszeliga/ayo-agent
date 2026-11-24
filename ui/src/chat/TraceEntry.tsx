import { ChevronRight } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useEffect, useRef } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { chunkLink, type FromChat } from '@/document/params'
import { useLanguage } from '@/layout/languageContext'
import { formatDecimal, formatUtc } from '@/lib/format'
import type { Language } from '@/lib/language'
import { cn } from '@/lib/utils'
import { chatCasePath } from '@/paths'

import { formatCost, formatDuration, formatTokens } from './format'
import { traceFlags } from './trace'

type CaseTurn = components['schemas']['CaseTurn']
type CaseToolCall = components['schemas']['CaseToolCall']
type CaseRetrievedChunk = components['schemas']['CaseRetrievedChunk']

interface Props {
  caseId: string
  turn: CaseTurn
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Opened from the turn's chip: outlined, and scrolled to on each new `focusNonce`. */
  focused: boolean
  focusNonce?: number
}

/** One turn's trace: a summary line that expands to its tool calls, retrieval and metrics. */
export function TraceEntry({ caseId, turn, open, onOpenChange, focused, focusNonce }: Props) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  const ref = useRef<HTMLLIElement>(null)
  const { trace } = turn
  const flags = traceFlags(trace)
  const phase =
    turn.phase_before === turn.phase_after
      ? t(`phase.${turn.phase_after}`)
      : t('phaseChange', {
          from: t(`phase.${turn.phase_before}`),
          to: t(`phase.${turn.phase_after}`),
        })

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'nearest' })
  }, [focused, focusNonce])

  return (
    <li
      ref={ref}
      aria-label={t('trace.entry', { n: turn.turn })}
      data-focused={focused || undefined}
      className={cn('rounded-md border text-sm', focused && 'border-primary ring-primary ring-1')}
    >
      <Collapsible open={open} onOpenChange={onOpenChange}>
        <CollapsibleTrigger className="hover:bg-accent/50 focus-visible:ring-ring/50 flex w-full items-start gap-2 rounded-md px-3 py-2 text-left outline-none focus-visible:ring-[3px]">
          <ChevronRight
            aria-hidden="true"
            className={cn('mt-0.5 size-4 flex-none transition-transform', open && 'rotate-90')}
          />
          <span className="min-w-0 flex-1 space-y-1">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-semibold">{t('turn.label', { n: turn.turn })}</span>
              <span className="text-muted-foreground">{phase}</span>
            </span>
            <span className="text-muted-foreground block text-xs">
              {[
                t('usage.calls', { count: trace.usage.llm_calls }),
                ...(trace.usage.cost !== null ? [formatCost(trace.usage.cost, language)] : []),
                formatDuration(trace.duration_ms, language),
              ].join(' · ')}
            </span>
            {(flags.capped || flags.retrievalFailed || flags.refused > 0) && (
              <span className="flex flex-wrap gap-1.5">
                {flags.capped && <Badge variant="warning">{t('trace.capped')}</Badge>}
                {flags.retrievalFailed && (
                  <Badge variant="warning">{t('trace.retrievalFailed')}</Badge>
                )}
                {flags.refused > 0 && (
                  <Badge variant="outline">{t('trace.refused', { count: flags.refused })}</Badge>
                )}
              </span>
            )}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 border-t px-3 py-3">
          <div role="group" aria-label={t('trace.toolCalls')} className="space-y-1.5">
            <h3 className="text-xs font-semibold">{t('trace.toolCalls')}</h3>
            {trace.tool_calls.length === 0 ? (
              <p className="text-muted-foreground text-xs italic">{t('trace.noCalls')}</p>
            ) : (
              <ul className="space-y-1">
                {trace.tool_calls.map((call, i) => (
                  <ToolCallRow key={i} call={call} t={t} />
                ))}
              </ul>
            )}
          </div>
          <div role="group" aria-label={t('trace.retrieved')} className="space-y-1.5">
            <h3 className="text-xs font-semibold">{t('trace.retrieved')}</h3>
            {trace.retrieval_error !== null && (
              <p className="text-warning text-xs">
                <Trans
                  t={t}
                  i18nKey="trace.searchFailed"
                  components={{ error: <code className="font-mono">{trace.retrieval_error}</code> }}
                />
              </p>
            )}
            {trace.retrieved.length === 0 ? (
              trace.retrieval_error === null && (
                <p className="text-muted-foreground text-xs italic">{t('trace.nothing')}</p>
              )
            ) : (
              <ul className="space-y-1">
                {trace.retrieved.map((chunk, i) => (
                  <RetrievedRow key={i} caseId={caseId} chunk={chunk} t={t} language={language} />
                ))}
              </ul>
            )}
          </div>
          <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
            <dt>{t('trace.detail.model')}</dt>
            <dd className="text-foreground font-mono break-all">
              {trace.model ?? t('trace.notReported')}
            </dd>
            <dt>{t('trace.detail.prompts')}</dt>
            <dd className="text-foreground font-mono break-all">{trace.prompts_version}</dd>
            <dt>{t('trace.detail.calls')}</dt>
            <dd className="text-foreground">{trace.usage.llm_calls}</dd>
            <dt>{t('trace.detail.tokens')}</dt>
            <dd className="text-foreground">{tokensLine(trace.usage, t, language)}</dd>
            <dt>{t('trace.detail.cost')}</dt>
            <dd className="text-foreground">
              {trace.usage.cost !== null
                ? formatCost(trace.usage.cost, language)
                : t('trace.notReported')}
            </dd>
            <dt>{t('trace.detail.duration')}</dt>
            <dd className="text-foreground">{formatDuration(trace.duration_ms, language)}</dd>
            <dt>{t('trace.detail.time')}</dt>
            <dd className="text-foreground">
              <time dateTime={turn.created_at}>{formatUtc(turn.created_at)}</time>
            </dd>
          </dl>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}

type ChatT = TFunction<'chat'>

function tokensLine(
  usage: components['schemas']['LLMUsage'],
  t: ChatT,
  language: Language,
): string {
  if (usage.total_tokens === null) return t('trace.notReported')
  const total = formatTokens(usage.total_tokens, language)
  if (usage.prompt_tokens === null || usage.completion_tokens === null) return total
  return t('trace.tokensInOut', {
    total,
    in: String(usage.prompt_tokens),
    out: String(usage.completion_tokens),
  })
}

function ToolCallRow({ call, t }: { call: CaseToolCall; t: ChatT }) {
  return (
    <li className="text-xs">
      <code className="font-mono">{call.name}</code>
      {call.target !== null && <span> → {t(`phase.${call.target}`)}</span>}{' '}
      {call.ok ? (
        <span className="text-success">{t('trace.accepted')}</span>
      ) : (
        <span className="text-warning">
          {t('trace.refusedCall')}
          {call.error_code !== null && (
            <>
              {' '}
              (<code className="font-mono">{call.error_code}</code>)
            </>
          )}
        </span>
      )}
      {call.missing.length > 0 && (
        <span className="text-muted-foreground">
          {' '}
          · {t('trace.missing')}{' '}
          {call.missing.map((code, i) => (
            <span key={code}>
              {i > 0 && ', '}
              <code className="font-mono">{code}</code>
            </span>
          ))}
        </span>
      )}
    </li>
  )
}

function RetrievedRow({
  caseId,
  chunk,
  t,
  language,
}: {
  caseId: string
  chunk: CaseRetrievedChunk
  t: ChatT
  language: Language
}) {
  const similarity = (
    <span className="text-muted-foreground font-mono tabular-nums">
      <span className="sr-only">{t('trace.similarity')}</span>
      {formatDecimal(chunk.similarity, language, { min: 2 })}
    </span>
  )
  if (chunk.document_deleted) {
    return (
      <li className="flex items-baseline gap-2 text-xs">
        {similarity}
        <span className="text-muted-foreground italic">{t('trace.deletedDocument')}</span>
      </li>
    )
  }
  const title = chunk.document_title ?? t('trace.untitledDocument')
  const from = chatCasePath(caseId)
  const changed = chunk.chunk_index === null
  const state: FromChat = changed
    ? { chatFrom: from }
    : { chatFrom: from, chunkIndex: chunk.chunk_index ?? 0 }
  return (
    <li className="flex items-baseline gap-2 text-xs">
      {similarity}
      <span className="min-w-0 break-words">
        <Link
          to={
            changed ? `/documents/${chunk.doc_id}` : chunkLink(chunk.doc_id, chunk.chunk_index ?? 0)
          }
          state={state}
          className={cn('hover:underline', chunk.document_title === null && 'italic')}
        >
          {title}
        </Link>{' '}
        {changed ? (
          <Badge variant="outline" title={t('trace.changedSinceTitle')}>
            {t('trace.changedSince')}
          </Badge>
        ) : (
          <span className="text-muted-foreground">
            {t('trace.chunk', { n: chunk.chunk_index })}
          </span>
        )}
      </span>
    </li>
  )
}

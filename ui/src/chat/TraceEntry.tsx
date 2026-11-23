import { ChevronRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router'

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { chunkLink, type FromChat } from '@/document/params'
import { formatUtc } from '@/lib/format'
import { cn } from '@/lib/utils'
import { chatCasePath } from '@/paths'

import { formatCost, formatDuration, formatTokens, plural } from './format'
import { PHASE_LABELS } from './phases'
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
  const ref = useRef<HTMLLIElement>(null)
  const { trace } = turn
  const flags = traceFlags(trace)
  const phase =
    turn.phase_before === turn.phase_after
      ? PHASE_LABELS[turn.phase_after]
      : `${PHASE_LABELS[turn.phase_before]} → ${PHASE_LABELS[turn.phase_after]}`

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'nearest' })
  }, [focused, focusNonce])

  return (
    <li
      ref={ref}
      aria-label={`Trace of turn ${String(turn.turn)}`}
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
              <span className="font-semibold">Turn {turn.turn}</span>
              <span className="text-muted-foreground">{phase}</span>
            </span>
            <span className="text-muted-foreground block text-xs">
              {[
                plural(trace.usage.llm_calls, 'call', 'calls'),
                ...(trace.usage.cost !== null ? [formatCost(trace.usage.cost)] : []),
                formatDuration(trace.duration_ms),
              ].join(' · ')}
            </span>
            {(flags.capped || flags.retrievalFailed || flags.refused > 0) && (
              <span className="flex flex-wrap gap-1.5">
                {flags.capped && <Badge variant="warning">Capped</Badge>}
                {flags.retrievalFailed && <Badge variant="warning">Retrieval failed</Badge>}
                {flags.refused > 0 && (
                  <Badge variant="outline">{String(flags.refused)} refused</Badge>
                )}
              </span>
            )}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 border-t px-3 py-3">
          <div role="group" aria-label="Tool calls" className="space-y-1.5">
            <h3 className="text-xs font-semibold">Tool calls</h3>
            {trace.tool_calls.length === 0 ? (
              <p className="text-muted-foreground text-xs italic">None</p>
            ) : (
              <ul className="space-y-1">
                {trace.tool_calls.map((call, i) => (
                  <ToolCallRow key={i} call={call} />
                ))}
              </ul>
            )}
          </div>
          <div role="group" aria-label="Retrieved" className="space-y-1.5">
            <h3 className="text-xs font-semibold">Retrieved</h3>
            {trace.retrieval_error !== null && (
              <p className="text-warning text-xs">
                The knowledge search failed:{' '}
                <code className="font-mono">{trace.retrieval_error}</code>
              </p>
            )}
            {trace.retrieved.length === 0 ? (
              trace.retrieval_error === null && (
                <p className="text-muted-foreground text-xs italic">Nothing</p>
              )
            ) : (
              <ul className="space-y-1">
                {trace.retrieved.map((chunk, i) => (
                  <RetrievedRow key={i} caseId={caseId} chunk={chunk} />
                ))}
              </ul>
            )}
          </div>
          <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
            <dt>Model</dt>
            <dd className="text-foreground font-mono break-all">{trace.model ?? 'Not reported'}</dd>
            <dt>Prompts</dt>
            <dd className="text-foreground font-mono break-all">{trace.prompts_version}</dd>
            <dt>Calls</dt>
            <dd className="text-foreground">{trace.usage.llm_calls}</dd>
            <dt>Tokens</dt>
            <dd className="text-foreground">{tokensLine(trace.usage)}</dd>
            <dt>Cost</dt>
            <dd className="text-foreground">
              {trace.usage.cost !== null ? formatCost(trace.usage.cost) : 'Not reported'}
            </dd>
            <dt>Duration</dt>
            <dd className="text-foreground">{formatDuration(trace.duration_ms)}</dd>
            <dt>Time</dt>
            <dd className="text-foreground">
              <time dateTime={turn.created_at}>{formatUtc(turn.created_at)}</time>
            </dd>
          </dl>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}

function tokensLine(usage: components['schemas']['LLMUsage']): string {
  if (usage.total_tokens === null) return 'Not reported'
  const parts =
    usage.prompt_tokens !== null && usage.completion_tokens !== null
      ? ` (${String(usage.prompt_tokens)} in, ${String(usage.completion_tokens)} out)`
      : ''
  return `${formatTokens(usage.total_tokens)}${parts}`
}

function ToolCallRow({ call }: { call: CaseToolCall }) {
  return (
    <li className="text-xs">
      <code className="font-mono">{call.name}</code>
      {call.target !== null && <span> → {PHASE_LABELS[call.target]}</span>}{' '}
      {call.ok ? (
        <span className="text-success">accepted</span>
      ) : (
        <span className="text-warning">
          refused
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
          · missing:{' '}
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

function RetrievedRow({ caseId, chunk }: { caseId: string; chunk: CaseRetrievedChunk }) {
  const similarity = (
    <span className="text-muted-foreground font-mono tabular-nums">
      <span className="sr-only">Similarity </span>
      {chunk.similarity.toFixed(2)}
    </span>
  )
  if (chunk.document_deleted) {
    return (
      <li className="flex items-baseline gap-2 text-xs">
        {similarity}
        <span className="text-muted-foreground italic">Deleted document</span>
      </li>
    )
  }
  const title = chunk.document_title ?? 'Untitled document'
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
          <Badge variant="outline" title="The document was reprocessed or replaced since this turn">
            Changed since
          </Badge>
        ) : (
          <span className="text-muted-foreground">· chunk #{chunk.chunk_index}</span>
        )}
      </span>
    </li>
  )
}

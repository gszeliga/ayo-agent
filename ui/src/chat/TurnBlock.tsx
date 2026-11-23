import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'
import { LazyMarkdown } from '@/document/LazyMarkdown'
import { formatUtc } from '@/lib/format'

import { PhaseMarker } from './PhaseMarker'

type CaseTurn = components['schemas']['CaseTurn']

/**
 * One turn: the user's message (plain text, never Markdown), the reply (through the safe
 * renderer), "Turn N · trace" opening its trace, and a marker when the turn changed phase.
 */
export function TurnBlock({
  turn,
  onShowTrace,
}: {
  turn: CaseTurn
  /** Opens this turn's trace in the inspector. */
  onShowTrace?: (turn: number) => void
}) {
  return (
    <li className="space-y-3" aria-label={`Turn ${String(turn.turn)}`}>
      <div className="flex justify-end">
        <p className="bg-primary/10 max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 break-words whitespace-pre-wrap">
          <span className="sr-only">User: </span>
          {turn.user_message.content}
        </p>
      </div>
      <div className="max-w-[90%]">
        <div className="bg-card rounded-2xl rounded-bl-sm border px-4 py-3">
          <span className="sr-only">Copilot: </span>
          <LazyMarkdown source={turn.reply.content} />
        </div>
        <div className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
          {onShowTrace ? (
            <button
              type="button"
              title={formatUtc(turn.created_at)}
              className="hover:text-foreground focus-visible:ring-ring/50 rounded-sm px-1 underline-offset-2 outline-none hover:underline focus-visible:ring-[3px]"
              onClick={() => {
                onShowTrace(turn.turn)
              }}
            >
              Turn {turn.turn} · trace
            </button>
          ) : (
            <span title={formatUtc(turn.created_at)}>Turn {turn.turn}</span>
          )}
          <CopyButton value={turn.reply.content} label="Copy reply" />
        </div>
      </div>
      {turn.phase_before !== turn.phase_after && (
        <PhaseMarker from={turn.phase_before} to={turn.phase_after} />
      )}
    </li>
  )
}

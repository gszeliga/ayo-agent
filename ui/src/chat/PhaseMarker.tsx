import { PHASE_LABELS, type Phase } from './phases'

/** A turn that changed phase: a quiet line after its reply. */
export function PhaseMarker({ from, to }: { from: Phase; to: Phase }) {
  return (
    <div className="text-muted-foreground flex items-center gap-3 text-xs">
      <span aria-hidden="true" className="bg-border h-px flex-1" />
      <span>
        Moved to <strong className="text-foreground font-medium">{PHASE_LABELS[to]}</strong> (from{' '}
        {PHASE_LABELS[from]})
      </span>
      <span aria-hidden="true" className="bg-border h-px flex-1" />
    </div>
  )
}

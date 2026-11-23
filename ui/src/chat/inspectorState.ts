import { useMediaQuery } from '@/hooks/useMediaQuery'

import type { useCaseTurns } from './queries'

export type InspectorTab = 'state' | 'actions' | 'trace' | 'summary'

/** From this width the inspector is a column beside the chat; below it, a drawer. */
export const WIDE_QUERY = '(min-width: 1024px)'

export function useWideScreen(): boolean {
  return useMediaQuery(WIDE_QUERY)
}

/** A trace opened from its turn's chip; a new `nonce` scrolls to it again. */
export interface TraceFocus {
  turn: number
  nonce: number
}

/** What the Trace tab needs from the case view, which keeps it while tabs switch. */
export interface TraceView {
  turns: ReturnType<typeof useCaseTurns>
  /** The open entries; null until the user opens or closes one (then the newest is open). */
  open: ReadonlySet<number> | null
  setOpen: (turn: number, open: boolean) => void
  focus: TraceFocus | null
}

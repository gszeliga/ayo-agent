import { Check } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { PHASE_LABELS, PHASES, type Phase } from './phases'

/** The five working phases; `closed` is shown as a badge after them. */
const STEPS: readonly Phase[] = PHASES.filter((phase) => phase !== 'closed')

type StepState = 'completed' | 'current' | 'not started'

function stepState(step: Phase, current: Phase): StepState {
  if (current === 'closed') return 'completed'
  const position = STEPS.indexOf(step)
  const now = STEPS.indexOf(current)
  if (position < now) return 'completed'
  return position === now ? 'current' : 'not started'
}

/** Where the case is: readable without colour (numbers, checks, words for screen readers). */
export function PhaseStepper({ phase }: { phase: Phase }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <ol aria-label="Phases" className="flex flex-wrap items-center gap-1">
        {STEPS.map((step, index) => {
          const state = stepState(step, phase)
          return (
            <li
              key={step}
              aria-current={state === 'current' ? 'step' : undefined}
              className="flex items-center gap-1"
            >
              {index > 0 && <span aria-hidden="true" className="bg-border h-px w-4" />}
              <span
                className={cn(
                  'flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium',
                  state === 'current' && 'border-primary bg-primary text-primary-foreground',
                  state === 'completed' && 'border-primary/40 text-primary',
                  state === 'not started' && 'text-muted-foreground',
                )}
              >
                <span aria-hidden="true" className="flex size-4 items-center justify-center">
                  {state === 'completed' ? <Check className="size-3.5" /> : index + 1}
                </span>
                {PHASE_LABELS[step]}
                <span className="sr-only"> ({state})</span>
              </span>
            </li>
          )
        })}
      </ol>
      {phase === 'closed' && <Badge variant="outline">Closed</Badge>}
    </div>
  )
}

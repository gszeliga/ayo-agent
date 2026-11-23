import { PanelRight, RefreshCw } from 'lucide-react'

import type { RefObject } from 'react'

import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { formatCost, formatTokens, plural } from './format'
import { PhaseStepper } from './PhaseStepper'

type CaseDetail = components['schemas']['CaseDetail']

interface Props {
  detail: CaseDetail
  refreshing: boolean
  onRefresh: () => void
  /** On wide screens the toggle shows or hides the column (pressed when shown); on narrow
   * ones it opens the drawer. */
  inspector: {
    wide: boolean
    shown: boolean
    onToggle: () => void
  }
  /** The inspector toggle: the drawer gives focus back to it when it closes. */
  toggleRef: RefObject<HTMLButtonElement | null>
}

/** Title, tenant, turns, what the case used, Refresh, the inspector toggle, the stepper. */
export function CaseHeader({ detail, refreshing, onRefresh, inspector, toggleRef }: Props) {
  const { cost, total_tokens: tokens } = detail.usage
  const facts = [
    detail.tenant,
    plural(detail.turns, 'turn', 'turns'),
    ...(cost !== null ? [formatCost(cost)] : []),
    ...(tokens !== null ? [formatTokens(tokens)] : []),
  ]
  return (
    <header className="space-y-3 border-b pb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1
            className={cn(
              'truncate text-lg font-semibold',
              detail.title === null && 'text-muted-foreground italic',
            )}
          >
            {detail.title ?? 'Untitled case'}
          </h1>
          <p className="text-muted-foreground text-[13px]" data-testid="case-facts">
            {facts.join(' · ')}
          </p>
        </div>
        <div className="flex flex-none gap-2">
          <Button variant="outline" disabled={refreshing} onClick={onRefresh}>
            <RefreshCw aria-hidden="true" className={cn(refreshing && 'animate-spin')} />
            Refresh
          </Button>
          <Button
            ref={toggleRef}
            variant="outline"
            onClick={inspector.onToggle}
            {...(inspector.wide
              ? { 'aria-pressed': inspector.shown }
              : { 'aria-haspopup': 'dialog' as const })}
          >
            <PanelRight aria-hidden="true" />
            Inspector
          </Button>
        </div>
      </div>
      <PhaseStepper phase={detail.phase} />
    </header>
  )
}

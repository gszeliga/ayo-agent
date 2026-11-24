import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/** The page edge a side panel sits on. */
export type PanelSide = 'left' | 'right'

const ICONS = {
  left: { hide: PanelLeftClose, show: PanelLeftOpen },
  right: { hide: PanelRightClose, show: PanelRightOpen },
} as const

/** An icon button with its name as a tooltip: every button of the panels and rails. */
export function PanelButton({
  label,
  tip = label,
  side,
  onClick,
  children,
  className,
  variant = 'ghost',
  ...aria
}: {
  label: string
  /** The tooltip, when it should say more than the name. */
  tip?: string
  /** Where the tooltip goes: towards the chat. */
  side: PanelSide
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void
  children: ReactNode
  className?: string
  variant?: 'ghost' | 'default'
  'aria-expanded'?: boolean
  'aria-haspopup'?: 'dialog'
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={variant}
          size="icon"
          aria-label={label}
          onClick={onClick}
          className={cn('relative', className)}
          {...aria}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side={side === 'left' ? 'right' : 'left'}>{tip}</TooltipContent>
    </Tooltip>
  )
}

/** The side panels a toggle hides or shows; their names are in the `chat` catalog. */
export type Panel = 'cases' | 'inspector'

/**
 * Hides or shows a side panel: "Hide cases" / "Show cases", "Hide inspector" / "Show
 * inspector" (whole phrases, so each language orders its words), the same icons mirrored, `aria-expanded` saying which. In a panel's header it
 * hides it; at the top of its rail it shows it.
 */
export function PanelToggle({
  side,
  panel,
  expanded,
  onClick,
  opensDialog = false,
}: {
  side: PanelSide
  panel: Panel
  expanded: boolean
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void
  /** Narrow screens: showing opens a drawer. */
  opensDialog?: boolean
}) {
  const { t } = useTranslation('chat')
  const Icon = ICONS[side][expanded ? 'hide' : 'show']
  return (
    <PanelButton
      label={expanded ? t(`panel.hide.${panel}`) : t(`panel.show.${panel}`)}
      side={side}
      onClick={onClick}
      aria-expanded={expanded}
      {...(opensDialog ? { 'aria-haspopup': 'dialog' as const } : {})}
    >
      <Icon aria-hidden="true" />
    </PanelButton>
  )
}

/** A collapsed side panel: a narrow column of buttons on its page edge, the toggle first. */
export function PanelRail({
  side,
  label,
  children,
}: {
  side: PanelSide
  /** "Cases list (collapsed)", "Inspector (collapsed)". */
  label: string
  children: ReactNode
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        'flex w-10 flex-none flex-col items-center gap-2',
        side === 'left' ? 'border-r pr-2' : 'border-l pl-2',
      )}
    >
      {children}
    </div>
  )
}

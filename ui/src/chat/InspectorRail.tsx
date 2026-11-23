import { Activity, ClipboardList, ListChecks, Sparkles } from 'lucide-react'

import type { components } from '@/api/schema'

import type { InspectorTab } from './inspectorState'
import { PanelButton, PanelRail, PanelToggle } from './PanelToggle'

type CaseDetail = components['schemas']['CaseDetail']

const TABS = [
  { tab: 'state', name: 'state', icon: ClipboardList },
  { tab: 'actions', name: 'actions', icon: ListChecks },
  { tab: 'trace', name: 'trace', icon: Activity },
  { tab: 'summary', name: 'summary', icon: Sparkles },
] as const

interface Props {
  detail: CaseDetail
  /** Narrow screens: every button opens the drawer. */
  drawer: boolean
  /** Opens the inspector: on `tab`, or on the tab it was left on. */
  onOpen: (tab?: InspectorTab) => void
}

/**
 * The collapsed inspector, on the right edge: Show inspector, then one button per tab. The
 * Actions button carries a dot when the API says an action is overdue (never recomputed).
 */
export function InspectorRail({ detail, drawer, onOpen }: Props) {
  const overdue = detail.actions.filter((action) => action.overdue).length
  return (
    <aside aria-label="Inspector (collapsed)" className="flex">
      <PanelRail side="right" label="Inspector tabs">
        <PanelToggle
          side="right"
          noun="inspector"
          expanded={false}
          opensDialog={drawer}
          onClick={() => {
            onOpen()
          }}
        />
        {TABS.map(({ tab, name, icon: Icon }) => {
          const late = tab === 'actions' && overdue > 0
          return (
            <PanelButton
              key={tab}
              side="right"
              label={late ? `Show ${name} (${String(overdue)} overdue)` : `Show ${name}`}
              onClick={() => {
                onOpen(tab)
              }}
              {...(drawer ? { 'aria-haspopup': 'dialog' as const } : {})}
            >
              <Icon aria-hidden="true" />
              {late && (
                <span
                  aria-hidden="true"
                  data-testid="overdue-dot"
                  className="bg-warning absolute top-1.5 right-1.5 size-2 rounded-full"
                />
              )}
            </PanelButton>
          )
        })}
      </PanelRail>
    </aside>
  )
}

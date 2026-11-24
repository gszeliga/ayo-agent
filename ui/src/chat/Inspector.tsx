import type { RefObject } from 'react'
import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import { ActionsTab } from './ActionsTab'
import type { InspectorTab, TraceView } from './inspectorState'
import { PanelResizer } from './PanelResizer'
import { PanelToggle } from './PanelToggle'
import { INSPECTOR_LIMITS } from './panelWidth'
import { StateTab } from './StateTab'
import { SummaryTab } from './SummaryTab'
import { TraceTab } from './TraceTab'

type CaseDetail = components['schemas']['CaseDetail']

interface TabsProps {
  detail: CaseDetail
  tab: InspectorTab
  onTabChange: (tab: InspectorTab) => void
  trace: TraceView
}

/** The tabs: what the case holds, from the case and turns already loaded. */
function InspectorTabs({ detail, tab, onTabChange, trace }: TabsProps) {
  const { t } = useTranslation('chat')
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => {
        onTabChange(value as InspectorTab)
      }}
      className="min-h-0 flex-1"
    >
      <TabsList aria-label={t('inspector.title')} className="w-full">
        <TabsTrigger value="state">{t('inspector.tabs.state')}</TabsTrigger>
        <TabsTrigger value="actions">{t('inspector.tabs.actions')}</TabsTrigger>
        <TabsTrigger value="trace">{t('inspector.tabs.trace')}</TabsTrigger>
        <TabsTrigger value="summary">{t('inspector.tabs.summary')}</TabsTrigger>
      </TabsList>
      <TabsContent value="state" className="min-h-0 overflow-y-auto pr-1">
        <StateTab detail={detail} />
      </TabsContent>
      <TabsContent value="actions" className="min-h-0 overflow-y-auto pr-1">
        <ActionsTab detail={detail} />
      </TabsContent>
      <TabsContent value="trace" className="min-h-0 overflow-y-auto pr-1">
        <TraceTab detail={detail} trace={trace} />
      </TabsContent>
      <TabsContent value="summary" className="min-h-0 overflow-y-auto pr-1">
        <SummaryTab detail={detail} />
      </TabsContent>
    </Tabs>
  )
}

interface PanelProps extends TabsProps {
  width: number
  onResize: (width: number) => void
  /** Collapses it to its rail. */
  onHide: () => void
}

/**
 * The inspector as a column beside the chat (wide screens), resized from its left edge.
 * CSS keeps it within 60% of the row too, should the window shrink after a resize.
 */
export function InspectorPanel({ width, onResize, onHide, ...props }: PanelProps) {
  const { t } = useTranslation('chat')
  return (
    <aside
      aria-label={t('inspector.title')}
      style={{ width }}
      className="relative flex max-w-[60%] min-w-80 flex-none flex-col pl-4"
    >
      <PanelResizer
        label={t('inspector.resize')}
        edge="left"
        width={width}
        limits={INSPECTOR_LIMITS}
        onResize={onResize}
      />
      {/* Mirrors the cases list's header: the toggle on the inner corner, by the chat. */}
      <div className="flex items-center gap-2 pb-3">
        <PanelToggle side="right" panel="inspector" expanded onClick={onHide} />
        <h2 className="font-semibold">{t('inspector.title')}</h2>
      </div>
      <InspectorTabs {...props} />
    </aside>
  )
}

interface DrawerProps extends TabsProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Where focus goes back on close: the button that opened it (Radix only knows its own
   * trigger). */
  returnFocusTo: RefObject<HTMLElement | null>
}

/** The inspector as a drawer from the right (narrow screens); Esc or Close shuts it. */
export function InspectorDrawer({ open, onOpenChange, returnFocusTo, ...props }: DrawerProps) {
  const { t } = useTranslation('chat')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          returnFocusTo.current?.focus()
        }}
        className="top-0 right-0 left-auto flex h-full w-full max-w-md translate-x-0 translate-y-0 flex-col rounded-none border-l sm:max-w-md data-[state=closed]:zoom-out-100 data-[state=open]:zoom-in-100"
      >
        <DialogTitle>{t('inspector.title')}</DialogTitle>
        <DialogDescription className="sr-only">
          {t('inspector.drawerDescription')}
        </DialogDescription>
        <InspectorTabs {...props} />
      </DialogContent>
    </Dialog>
  )
}

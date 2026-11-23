import type { RefObject } from 'react'

import type { components } from '@/api/schema'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import { ActionsTab } from './ActionsTab'
import type { InspectorTab, TraceView } from './inspectorState'
import { PanelResizer } from './PanelResizer'
import { INSPECTOR_LIMITS } from './panelWidth'
import { StateTab } from './StateTab'
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
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => {
        onTabChange(value as InspectorTab)
      }}
      className="min-h-0 flex-1"
    >
      <TabsList aria-label="Inspector" className="w-full">
        <TabsTrigger value="state">State</TabsTrigger>
        <TabsTrigger value="actions">Actions</TabsTrigger>
        <TabsTrigger value="trace">Trace</TabsTrigger>
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
    </Tabs>
  )
}

interface PanelProps extends TabsProps {
  width: number
  onResize: (width: number) => void
}

/**
 * The inspector as a column beside the chat (wide screens), resized from its left edge.
 * CSS keeps it within 60% of the row too, should the window shrink after a resize.
 */
export function InspectorPanel({ width, onResize, ...props }: PanelProps) {
  return (
    <aside
      aria-label="Inspector"
      style={{ width }}
      className="relative flex max-w-[60%] min-w-80 flex-none flex-col pl-4"
    >
      <PanelResizer
        label="Resize inspector"
        edge="left"
        width={width}
        limits={INSPECTOR_LIMITS}
        onResize={onResize}
      />
      <InspectorTabs {...props} />
    </aside>
  )
}

interface DrawerProps extends TabsProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Where focus goes back on close: the toggle (Radix only knows its own trigger). */
  returnFocusTo: RefObject<HTMLElement | null>
}

/** The inspector as a drawer from the right (narrow screens); Esc or Close shuts it. */
export function InspectorDrawer({ open, onOpenChange, returnFocusTo, ...props }: DrawerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          returnFocusTo.current?.focus()
        }}
        className="top-0 right-0 left-auto flex h-full w-full max-w-md translate-x-0 translate-y-0 flex-col rounded-none border-l sm:max-w-md data-[state=closed]:zoom-out-100 data-[state=open]:zoom-in-100"
      >
        <DialogTitle>Inspector</DialogTitle>
        <DialogDescription className="sr-only">
          What the case holds: its facts, annotations, actions and turn traces.
        </DialogDescription>
        <InspectorTabs {...props} />
      </DialogContent>
    </Dialog>
  )
}

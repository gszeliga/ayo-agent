import { useOutletContext } from 'react-router'

import type { InspectorTab } from './inspectorState'

/** A conversation not sent yet: its session and tenant, in memory only. */
export interface Draft {
  sessionId: string
  tenant: string
}

/** What the chat page shares with the views inside it. */
export interface ChatContext {
  draft: Draft | null
  clearDraft: () => void
  openNewConversation: () => void
  /** The inspector: hidden or not on wide screens and its tab (memory), its width (also
   * in localStorage, a number only). */
  inspector: InspectorState
}

export interface InspectorState {
  hidden: boolean
  setHidden: (hidden: boolean) => void
  tab: InspectorTab
  setTab: (tab: InspectorTab) => void
  width: number
  setWidth: (width: number) => void
}

export function useChatContext(): ChatContext {
  return useOutletContext<ChatContext>()
}

import { useOutletContext } from 'react-router'

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
}

export function useChatContext(): ChatContext {
  return useOutletContext<ChatContext>()
}

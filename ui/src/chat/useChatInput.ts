import { useState } from 'react'

import type { components } from '@/api/schema'

import { useSendMessage } from './useSendMessage'

type CopilotMessageResponse = components['schemas']['CopilotMessageResponse']

/**
 * The message box of one conversation: the text, sending it, and putting it back when the
 * turn fails (nothing of a failed turn is stored). The text lives in this component's
 * state only, never in browser storage.
 */
export function useChatInput(
  target: { sessionId: string; tenant: string },
  onAnswered?: (response: CopilotMessageResponse) => void,
) {
  const send = useSendMessage()
  const [text, setText] = useState('')

  function submit() {
    const message = text.trim()
    if (message === '' || send.isPending) return
    setText('')
    // These callbacks run only while this conversation is shown (decision: no alert on
    // another case); the caches are updated by the mutation itself either way.
    send.mutate(
      { ...target, text: message },
      {
        onError: () => {
          setText(message)
        },
        onSuccess: (response) => {
          onAnswered?.(response)
        },
      },
    )
  }

  return {
    text,
    setText,
    submit,
    sending: send.isPending,
    pendingText: send.isPending ? send.variables.text : null,
    error: send.error,
    /** Forgets the last error (after a reload). */
    clearError: send.reset,
  }
}

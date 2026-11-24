import { MessageSquarePlus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { chatCasePath } from '@/paths'

import { useChatContext, type Draft } from './chatContext'
import { Composer } from './Composer'
import { PendingTurn } from './PendingTurn'
import { SendError } from './SendError'
import { useChatInput } from './useChatInput'

/**
 * `/chat/new`: a conversation before its first message. The case exists once the copilot
 * answers; then its page replaces this one. Without a draft (a reload, a pasted link) it
 * offers to start one.
 */
export function NewConversation() {
  const { t } = useTranslation('chat')
  const { draft, openNewConversation } = useChatContext()
  if (draft === null) {
    return (
      <EmptyState
        as="h1"
        title={t('newConversation.noDraftTitle')}
        description={t('newConversation.noDraftDescription')}
        className="mx-auto mt-10 max-w-xl"
        action={<Button onClick={openNewConversation}>{t('newConversation.title')}</Button>}
      />
    )
  }
  // Keyed: a second "New conversation" starts from an empty box.
  return <DraftConversation key={draft.sessionId} draft={draft} />
}

function DraftConversation({ draft }: { draft: Draft }) {
  const { t } = useTranslation('chat')
  const navigate = useNavigate()
  const { clearDraft } = useChatContext()
  const input = useChatInput(draft, (response) => {
    void navigate(chatCasePath(response.case_id), { replace: true })
    clearDraft()
  })

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <header className="border-b pb-3">
        <h1 className="text-lg font-semibold">{t('newConversation.title')}</h1>
        <p className="text-muted-foreground text-[13px]">{draft.tenant}</p>
      </header>
      <div className="flex min-h-0 flex-1 flex-col-reverse overflow-y-auto pr-1">
        <div role="log" aria-live="polite" aria-label={t('conversation')} className="py-2">
          {input.pendingText !== null ? (
            <PendingTurn text={input.pendingText} />
          ) : (
            <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-center">
              <MessageSquarePlus aria-hidden="true" className="size-6" />
              <p>{t('newConversation.firstMessage')}</p>
            </div>
          )}
        </div>
      </div>
      <div className="space-y-2">
        {input.error && !input.sending && (
          <SendError error={input.error} onSendAgain={input.submit} />
        )}
        <Composer
          value={input.text}
          onChange={input.setText}
          onSend={input.submit}
          sending={input.sending}
        />
      </div>
    </div>
  )
}

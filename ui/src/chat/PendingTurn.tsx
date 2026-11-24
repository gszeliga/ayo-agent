import { useTranslation } from 'react-i18next'

/** The message being answered: shown as sent, not saved yet, with a typing indicator. */
export function PendingTurn({ text }: { text: string }) {
  const { t } = useTranslation('chat')
  return (
    <div className="space-y-3" data-testid="pending-turn">
      <div className="flex flex-col items-end gap-1">
        <p className="bg-primary/10 max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 break-words whitespace-pre-wrap opacity-70">
          <span className="sr-only">{t('turn.user')}</span>
          {text}
        </p>
        <span className="text-muted-foreground text-xs">{t('pending.sending')}</span>
      </div>
      <div
        role="status"
        className="bg-card text-muted-foreground inline-flex items-center gap-1 rounded-2xl rounded-bl-sm border px-4 py-3"
      >
        <span className="sr-only">{t('pending.answering')}</span>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            aria-hidden="true"
            className="size-1.5 animate-bounce rounded-full bg-current"
            style={{ animationDelay: `${String(i * 150)}ms` }}
          />
        ))}
      </div>
    </div>
  )
}

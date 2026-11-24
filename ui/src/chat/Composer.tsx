import { SendHorizontal } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface Props {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  sending: boolean
}

/** The message box: Enter sends, Shift+Enter adds a line. Disabled while a turn runs. */
export function Composer({ value, onChange, onSend, sending }: Props) {
  const { t } = useTranslation('chat')
  const empty = value.trim() === ''
  return (
    <form
      className="space-y-1.5"
      onSubmit={(event) => {
        event.preventDefault()
        if (!empty && !sending) onSend()
      }}
    >
      <div className="flex items-end gap-2">
        <label htmlFor="chat-message" className="sr-only">
          {t('composer.label')}
        </label>
        <textarea
          id="chat-message"
          rows={2}
          disabled={sending}
          // The conversation's language (the copilot speaks Spanish), in every UI language.
          placeholder="Escribe un mensaje…"
          className={cn(
            'border-input placeholder:text-muted-foreground dark:bg-input/30 block max-h-48 min-h-14 w-full flex-1 resize-y rounded-md border bg-transparent px-3 py-2 text-base shadow-xs outline-none md:text-sm',
            'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
            'disabled:opacity-60',
          )}
          value={value}
          onChange={(event) => {
            onChange(event.target.value)
          }}
          onKeyDown={(event) => {
            if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
            event.preventDefault()
            if (!empty && !sending) onSend()
          }}
        />
        <Button type="submit" disabled={empty || sending}>
          <SendHorizontal aria-hidden="true" />
          {t('composer.send')}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">{t('composer.hint')}</p>
    </form>
  )
}

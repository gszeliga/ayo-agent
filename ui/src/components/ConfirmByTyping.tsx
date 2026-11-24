import { useId } from 'react'
import { Trans } from 'react-i18next'

import { Input } from '@/components/ui/input'

/** "Type X to confirm": a deliberate step before something that can't be undone. */
export function ConfirmByTyping({
  expected,
  value,
  onChange,
  disabled,
}: {
  expected: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}) {
  const id = useId()
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-[13px]">
        <Trans
          i18nKey="confirmByTyping"
          components={{
            phrase: <strong className="font-mono font-semibold break-all">{expected}</strong>,
          }}
        />
      </label>
      <Input
        id={id}
        autoComplete="off"
        spellCheck={false}
        className="font-mono"
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value)
        }}
      />
    </div>
  )
}

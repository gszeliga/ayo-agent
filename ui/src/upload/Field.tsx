import { useId, type ReactNode } from 'react'

import { Label } from '@/components/ui/label'

/** A label, a control, and its hint or error underneath, wired for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: (props: {
    id: string
    'aria-invalid': true | undefined
    'aria-describedby': string | undefined
  }) => ReactNode
}) {
  const id = useId()
  const noteId = useId()
  const note = error ?? hint
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': note ? noteId : undefined,
      })}
      {note && (
        <p
          id={noteId}
          className={error ? 'text-destructive text-[13px]' : 'text-muted-foreground text-[13px]'}
        >
          {note}
        </p>
      )}
    </div>
  )
}

import { Lock } from 'lucide-react'

export function ReadOnlyNotice({ reason }: { reason: string }) {
  return (
    <p
      role="note"
      className="bg-muted text-muted-foreground flex items-center gap-2 rounded-md px-3 py-2 text-[13px]"
    >
      <Lock aria-hidden="true" className="size-4 flex-none" />
      {reason}
    </p>
  )
}

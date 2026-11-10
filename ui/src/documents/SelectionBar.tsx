import { RefreshCw, Trash2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function SelectionBar({
  count,
  offPage,
  onClear,
  onReprocess,
  onDelete,
}: {
  count: number
  /** How many of them are on other pages. */
  offPage: number
  onClear: () => void
  onReprocess: () => void
  onDelete: () => void
}) {
  return (
    <div
      role="region"
      aria-label="Selection"
      className="border-primary bg-primary/5 flex flex-wrap items-center gap-3 rounded-lg border py-1.5 pr-1.5 pl-4"
    >
      <p className="flex-1 font-medium">
        {count} selected
        {offPage > 0 && (
          <span className="text-muted-foreground font-normal"> ({offPage} on other pages)</span>
        )}
      </p>
      <Button variant="ghost" onClick={onClear}>
        <X aria-hidden="true" />
        Clear selection
      </Button>
      <Button variant="outline" onClick={onReprocess}>
        <RefreshCw aria-hidden="true" />
        Reprocess
      </Button>
      <Button variant="destructive" onClick={onDelete}>
        <Trash2 aria-hidden="true" />
        Delete
      </Button>
    </div>
  )
}

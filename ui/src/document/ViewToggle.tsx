import { cn } from '@/lib/utils'

import type { View } from './params'

const VIEWS: { value: View; label: string }[] = [
  { value: 'rendered', label: 'Rendered' },
  { value: 'raw', label: 'Raw' },
]

/** Rendered / Raw, for the content and for the chunks. */
export function ViewToggle({
  view,
  onView,
  label,
  order = 'rendered-first',
}: {
  view: View
  onView: (view: View) => void
  /** Names the group for screen readers: "Content view". */
  label: string
  /** The default comes first. */
  order?: 'rendered-first' | 'raw-first'
}) {
  const views = order === 'raw-first' ? [...VIEWS].reverse() : VIEWS
  return (
    <div role="group" aria-label={label} className="bg-secondary inline-flex rounded-md p-0.5">
      {views.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={view === option.value}
          className={cn(
            'text-muted-foreground min-h-7 rounded-sm px-2.5 text-[13px] font-medium',
            view === option.value && 'bg-card text-foreground shadow-xs',
          )}
          onClick={() => {
            onView(option.value)
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

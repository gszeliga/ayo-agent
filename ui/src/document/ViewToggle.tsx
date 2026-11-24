import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

import type { View } from './params'

const VIEWS: readonly View[] = ['rendered', 'raw']

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
  const { t } = useTranslation('document')
  const views = order === 'raw-first' ? [...VIEWS].reverse() : VIEWS
  return (
    <div role="group" aria-label={label} className="bg-secondary inline-flex rounded-md p-0.5">
      {views.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={view === option}
          className={cn(
            'text-muted-foreground min-h-7 rounded-sm px-2.5 text-[13px] font-medium',
            view === option && 'bg-card text-foreground shadow-xs',
          )}
          onClick={() => {
            onView(option)
          }}
        >
          {t(`view.${option}`)}
        </button>
      ))}
    </div>
  )
}

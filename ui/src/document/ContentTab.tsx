import { lazy, Suspense, useEffect } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { CopyButton } from '@/components/CopyButton'
import { cn } from '@/lib/utils'

import { isNotFound } from './errors'
import type { View } from './params'
import { useContent } from './queries'
import { TabError } from './TabError'

// The Markdown libraries are most of the bundle's weight and only this view needs them.
const Markdown = lazy(() => import('./Markdown').then((module) => ({ default: module.Markdown })))

const VIEWS: { value: View; label: string }[] = [
  { value: 'rendered', label: 'Rendered' },
  { value: 'raw', label: 'Raw' },
]

export function ContentTab({
  docId,
  onGone,
  view,
  onView,
}: {
  docId: string
  /** The document was deleted meanwhile (a 404). */
  onGone: () => void
  view: View
  onView: (view: View) => void
}) {
  const content = useContent(docId, true)
  const gone = isNotFound(content.error)
  useEffect(() => {
    if (gone) onGone()
  }, [gone, onGone])
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div role="group" aria-label="View" className="bg-secondary inline-flex rounded-md p-0.5">
          {VIEWS.map((option) => (
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
        {view === 'raw' && content.data !== undefined && (
          <CopyButton value={content.data} label="Copy Markdown" />
        )}
      </div>
      {content.isError ? (
        <TabError error={content.error} onRetry={() => void content.refetch()} />
      ) : content.data === undefined ? (
        <div aria-busy="true" aria-label="Loading content" className="space-y-2">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
        </div>
      ) : view === 'raw' ? (
        <pre className="bg-secondary max-h-[560px] overflow-auto rounded-lg p-4 font-mono text-[12.5px] break-words whitespace-pre-wrap">
          {content.data}
        </pre>
      ) : (
        <Suspense fallback={<Skeleton aria-label="Loading content" className="h-24" />}>
          <Markdown source={content.data} />
        </Suspense>
      )}
    </div>
  )
}

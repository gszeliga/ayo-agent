import { useEffect } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { CopyButton } from '@/components/CopyButton'

import { isNotFound } from './errors'
import { LazyMarkdown } from './LazyMarkdown'
import type { View } from './params'
import { useContent } from './queries'
import { TabError } from './TabError'
import { ViewToggle } from './ViewToggle'

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
        <ViewToggle view={view} onView={onView} label="Content view" />
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
        <LazyMarkdown source={content.data} />
      )}
    </div>
  )
}

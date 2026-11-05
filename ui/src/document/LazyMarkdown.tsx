import { lazy, Suspense } from 'react'

import { Skeleton } from '@/components/ui/skeleton'

// The Markdown libraries are most of the bundle's weight; only rendered views need them.
const Markdown = lazy(() => import('./Markdown').then((module) => ({ default: module.Markdown })))

/** The safe Markdown renderer (Markdown.tsx), loaded on first use. */
export function LazyMarkdown({ source }: { source: string }) {
  return (
    <Suspense fallback={<Skeleton aria-label="Loading content" className="h-16" />}>
      <Markdown source={source} />
    </Suspense>
  )
}

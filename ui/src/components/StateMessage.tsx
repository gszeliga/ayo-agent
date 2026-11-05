import type { ReactNode } from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Nothing to show (no documents, no match, not found): a centred card. */
export function EmptyState({
  title,
  description,
  action,
  as: Heading = 'h2',
  className,
}: {
  title: string
  description?: ReactNode
  action?: ReactNode
  as?: 'h1' | 'h2'
  className?: string
}) {
  return (
    <section className={cn('bg-card rounded-xl border px-6 py-10 text-center', className)}>
      <Heading className="font-semibold">{title}</Heading>
      {description && <p className="text-muted-foreground mt-1.5">{description}</p>}
      {action && <div className="mt-4 flex justify-center gap-2">{action}</div>}
    </section>
  )
}

/** A failed load, where the data would be, with Retry. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert variant="destructive" role="alert">
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>{message}</span>
        {onRetry && (
          <Button variant="outline" onClick={onRetry}>
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

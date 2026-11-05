import { Link } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export function NotFoundPage() {
  useDocumentTitle('Page not found')
  return (
    <EmptyState
      as="h1"
      title="Page not found"
      description="There is nothing at this address."
      className="mx-auto mt-8 max-w-xl"
      action={
        <Button asChild variant="outline">
          <Link to="/documents">Go to documents</Link>
        </Button>
      }
    />
  )
}

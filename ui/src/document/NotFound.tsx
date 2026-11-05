import { Link } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export function DocumentNotFound({ back }: { back: string }) {
  useDocumentTitle('Document not found')
  return (
    <EmptyState
      as="h1"
      title="This document no longer exists"
      description="It may have been deleted in another tab, or the link is wrong."
      className="mx-auto mt-8 max-w-xl"
      action={
        <Button asChild>
          <Link to={back}>Back to documents</Link>
        </Button>
      }
    />
  )
}

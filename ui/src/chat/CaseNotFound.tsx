import { Link } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { ROUTES } from '@/paths'

/** An unknown or malformed case id: deleted, or the link is wrong. */
export function CaseNotFound() {
  return (
    <EmptyState
      as="h1"
      title="This case no longer exists"
      description="It may have been deleted, or the link is wrong."
      className="mx-auto mt-10 max-w-xl"
      action={
        <Button asChild>
          <Link to={ROUTES.chat}>Back to the cases</Link>
        </Button>
      }
    />
  )
}

import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <section className="space-y-3">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground">There is nothing at this address.</p>
      <Button asChild variant="outline">
        <Link to="/documents">Go to documents</Link>
      </Button>
    </section>
  )
}

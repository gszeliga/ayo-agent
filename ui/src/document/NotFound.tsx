import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function DocumentNotFound({ back }: { back: string }) {
  return (
    <section className="bg-card mx-auto mt-8 max-w-xl rounded-xl border px-6 py-12 text-center">
      <h1 className="text-base font-semibold">This document no longer exists</h1>
      <p className="text-muted-foreground mt-1.5">
        It may have been deleted in another tab, or the link is wrong.
      </p>
      <Button asChild className="mt-4">
        <Link to={back}>Back to documents</Link>
      </Button>
    </section>
  )
}

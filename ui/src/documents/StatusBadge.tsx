import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { OUTDATED_REASONS } from './status'

type Document = components['schemas']['Document']

/** Green "Indexed", or amber "Outdated" with the reason in a tooltip (and for screen readers). */
export function StatusBadge({
  document,
}: {
  document: Pick<Document, 'status' | 'outdated_reason'>
}) {
  if (document.status === 'indexed') return <Badge variant="success">Indexed</Badge>
  const reason = OUTDATED_REASONS[document.outdated_reason ?? 'unknown']
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="warning" tabIndex={0}>
          Outdated<span className="sr-only">: {reason}</span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  )
}

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'

type CaseDetail = components['schemas']['CaseDetail']

/**
 * The case's actions, oldest first as the API gives them, one card each so they fit any
 * inspector width. `overdue` is the API's value, never recomputed here: the API decides it
 * in the plant's time zone.
 */
export function ActionsTab({ detail }: { detail: CaseDetail }) {
  if (detail.actions.length === 0) {
    return <p className="text-muted-foreground text-sm italic">No actions yet</p>
  }
  return (
    <ul aria-label="Actions" className="space-y-2">
      {detail.actions.map((action) => (
        <li key={action.id} className="space-y-2 rounded-md border px-3 py-2 text-sm">
          <p className="break-words whitespace-pre-wrap">{action.description}</p>
          <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
            <dt>Owner</dt>
            <dd className="text-foreground break-words">{action.owner}</dd>
            <dt>Due</dt>
            <dd className="text-foreground">
              <time dateTime={action.due_date}>{action.due_date}</time>
            </dd>
          </dl>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant={action.status === 'done' ? 'success' : 'outline'}>
              {action.status === 'done' ? 'Done' : 'Pending'}
            </Badge>
            {action.overdue && <Badge variant="warning">Overdue</Badge>}
          </div>
        </li>
      ))}
    </ul>
  )
}

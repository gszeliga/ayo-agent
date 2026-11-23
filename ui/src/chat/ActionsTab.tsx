import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

type CaseDetail = components['schemas']['CaseDetail']

/**
 * The case's actions, oldest first as the API gives them. `overdue` is the API's value,
 * never recomputed here: the API decides it in the plant's time zone.
 */
export function ActionsTab({ detail }: { detail: CaseDetail }) {
  if (detail.actions.length === 0) {
    return <p className="text-muted-foreground text-sm italic">No actions yet</p>
  }
  return (
    <Table aria-label="Actions">
      <TableHeader>
        <TableRow>
          <TableHead>Action</TableHead>
          <TableHead>Owner</TableHead>
          <TableHead>Due</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {detail.actions.map((action) => (
          <TableRow key={action.id}>
            <TableCell className="min-w-32 align-top whitespace-pre-wrap">
              {action.description}
            </TableCell>
            <TableCell className="align-top whitespace-normal">{action.owner}</TableCell>
            <TableCell className="align-top">
              <time dateTime={action.due_date}>{action.due_date}</time>
            </TableCell>
            <TableCell className="space-y-1 align-top">
              <Badge variant={action.status === 'done' ? 'success' : 'outline'}>
                {action.status === 'done' ? 'Done' : 'Pending'}
              </Badge>
              {action.overdue && (
                <div>
                  <Badge variant="warning">Overdue</Badge>
                </div>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

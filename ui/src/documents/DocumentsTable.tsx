import { Link, useNavigate } from 'react-router'

import type { components } from '@/api/schema'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatBytes, formatUtc, relativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

import { StatusBadge } from './StatusBadge'

type Document = components['schemas']['Document']

const SKELETON_ROWS = 6

function Head() {
  return (
    <TableHeader>
      <TableRow>
        <TableHead>Document</TableHead>
        <TableHead>Tenant</TableHead>
        <TableHead>Status</TableHead>
        <TableHead className="text-right">Chunks</TableHead>
        <TableHead className="text-right">Size</TableHead>
        <TableHead>Updated</TableHead>
      </TableRow>
    </TableHeader>
  )
}

export function DocumentsTableSkeleton() {
  return (
    <Table aria-busy="true" aria-label="Loading documents">
      <Head />
      <TableBody>
        {Array.from({ length: SKELETON_ROWS }, (_, i) => (
          <TableRow key={i}>
            <TableCell>
              <Skeleton className="mb-1.5 h-3 w-3/4" />
              <Skeleton className="h-2.5 w-2/5" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-3 w-20" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-5 w-16 rounded-full" />
            </TableCell>
            <TableCell>
              <Skeleton className="ml-auto h-3 w-8" />
            </TableCell>
            <TableCell>
              <Skeleton className="ml-auto h-3 w-12" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-3 w-16" />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function DocumentsTable({
  documents,
  busy,
  now,
}: {
  documents: Document[]
  busy: boolean
  /** "Now" for relative times: when the data was fetched, so a render stays pure. */
  now: number
}) {
  const navigate = useNavigate()
  return (
    <Table aria-busy={busy} aria-label="Documents" className={cn(busy && 'opacity-60')}>
      <Head />
      <TableBody>
        {documents.map((doc) => {
          const to = `/documents/${doc.doc_id}`
          return (
            <TableRow
              key={doc.doc_id}
              className="cursor-pointer"
              // A convenience for the mouse; the title link is the keyboard and reader path.
              onClick={(event) => {
                if (!(event.target as HTMLElement).closest('a, button, [tabindex]')) {
                  void navigate(to)
                }
              }}
            >
              <TableCell className="max-w-0 min-w-64">
                <Link to={to} className="block truncate font-medium hover:underline">
                  {doc.title ?? doc.source_key}
                </Link>
                <div className="text-muted-foreground truncate font-mono text-[12px]">
                  {doc.source_key}
                </div>
              </TableCell>
              <TableCell>
                <span className="bg-secondary text-muted-foreground rounded-sm px-2 py-0.5 text-xs font-medium">
                  {doc.tenant}
                </span>
              </TableCell>
              <TableCell>
                <StatusBadge document={doc} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{doc.chunk_count}</TableCell>
              <TableCell className="text-right tabular-nums">
                {doc.size_bytes === null ? '—' : formatBytes(doc.size_bytes)}
              </TableCell>
              <TableCell>
                <time dateTime={doc.updated_at} title={formatUtc(doc.updated_at)}>
                  {relativeTime(doc.updated_at, now)}
                </time>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

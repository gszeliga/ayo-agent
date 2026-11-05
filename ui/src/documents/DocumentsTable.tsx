import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import type { components } from '@/api/schema'
import { Checkbox } from '@/components/ui/checkbox'
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
import type { Selection } from './useSelection'

type Document = components['schemas']['Document']

const SKELETON_ROWS = 6

function Head({ selectAll }: { selectAll?: ReactNode }) {
  return (
    <TableHeader>
      <TableRow>
        <TableHead className="w-10">{selectAll}</TableHead>
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
            <TableCell />
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
  selection,
}: {
  documents: Document[]
  busy: boolean
  /** "Now" for relative times: when the data was fetched, so a render stays pure. */
  now: number
  selection: Selection
}) {
  const onPage = documents.filter((doc) => selection.has(doc.doc_id)).length
  const allOnPage = documents.length > 0 && onPage === documents.length
  const navigate = useNavigate()
  // The detail's "← Documents" returns to the list as it is now.
  const state = { listSearch: useLocation().search || '?' }
  return (
    <Table aria-busy={busy} aria-label="Documents" className={cn(busy && 'opacity-60')}>
      <Head
        selectAll={
          <Checkbox
            aria-label="Select all on this page"
            checked={allOnPage ? true : onPage > 0 ? 'indeterminate' : false}
            onCheckedChange={() => {
              selection.setAll(documents, !allOnPage)
            }}
          />
        }
      />
      <TableBody>
        {documents.map((doc) => {
          const to = `/documents/${doc.doc_id}`
          return (
            <TableRow
              key={doc.doc_id}
              data-state={selection.has(doc.doc_id) ? 'selected' : undefined}
              className="cursor-pointer"
              // A convenience for the mouse; the title link is the keyboard and reader path.
              onClick={(event) => {
                if (!(event.target as HTMLElement).closest('a, button, [tabindex]')) {
                  void navigate(to, { state })
                }
              }}
            >
              <TableCell>
                <Checkbox
                  aria-label={`Select ${doc.title ?? doc.source_key}`}
                  checked={selection.has(doc.doc_id)}
                  onCheckedChange={() => {
                    selection.toggle(doc)
                  }}
                />
              </TableCell>
              <TableCell className="max-w-0 min-w-64">
                <Link to={to} state={state} className="block truncate font-medium hover:underline">
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

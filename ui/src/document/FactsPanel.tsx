import type { ReactNode } from 'react'

import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'
import { formatBytes, formatUtc, relativeTime } from '@/lib/format'

type Document = components['schemas']['Document']

const NOT_RECORDED = <span className="text-muted-foreground italic">not recorded</span>

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-muted-foreground text-xs font-medium">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  )
}

function Time({ iso, now }: { iso: string | null; now: number }) {
  if (iso === null) return NOT_RECORDED
  return (
    <time dateTime={iso} title={formatUtc(iso)}>
      {relativeTime(iso, now)}
    </time>
  )
}

/** A long value shortened to 12 characters, the full one copied. */
function Hash({ value, label }: { value: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <code className="font-mono text-[12.5px]" title={value}>
        {value.slice(0, 12)}…
      </code>
      <CopyButton value={value} label={`Copy ${label}`} />
    </span>
  )
}

function Config({ value }: { value: string | null }) {
  if (value === null) return NOT_RECORDED
  return <code className="font-mono text-[12.5px] break-all">{value}</code>
}

export function FactsPanel({ document, now }: { document: Document; now: number }) {
  return (
    <aside aria-label="Facts" className="bg-card rounded-xl border p-5">
      <dl className="space-y-4">
        <Fact label="Source key">
          <code className="font-mono text-[12.5px] break-all">{document.source_key}</code>
        </Fact>
        <Fact label="Created">
          <Time iso={document.created_at} now={now} />
        </Fact>
        <Fact label="Updated">
          <Time iso={document.updated_at} now={now} />
        </Fact>
        <Fact label="Chunked / embedded">
          <Time iso={document.chunked_at} now={now} /> /{' '}
          <Time iso={document.embedded_at} now={now} />
        </Fact>
        <Fact label="Size">
          {document.size_bytes === null ? NOT_RECORDED : formatBytes(document.size_bytes)}
        </Fact>
        <Fact label="Chunks">{document.chunk_count}</Fact>
        <Fact label="Content hash">
          <Hash value={document.content_hash} label="content hash" />
        </Fact>
        <Fact label="Embed signature">
          <Hash value={document.embed_signature} label="embed signature" />
        </Fact>
        <Fact label="Chunker config">
          <Config value={document.chunker_config} />
        </Fact>
        <Fact label="Embedder config">
          <Config value={document.embedder_config} />
        </Fact>
      </dl>
    </aside>
  )
}

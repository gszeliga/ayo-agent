import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'

type Chunk = components['schemas']['Chunk']

const VECTOR_PREVIEW = 12

export function ChunkCard({ chunk }: { chunk: Chunk }) {
  return (
    <article
      aria-label={`Chunk ${String(chunk.chunk_index)}`}
      className="bg-card space-y-2 rounded-xl border p-4"
    >
      <header className="text-muted-foreground flex flex-wrap items-baseline gap-x-3 text-[13px]">
        <span className="text-foreground font-mono font-semibold">#{chunk.chunk_index}</span>
        {chunk.heading && <span className="min-w-0 flex-1 truncate">{chunk.heading}</span>}
        <span className="ml-auto tabular-nums">{chunk.char_count} chars</span>
      </header>
      <p className="whitespace-pre-wrap">{chunk.chunk_text}</p>
      {chunk.embedding && (
        <div className="bg-secondary flex items-center gap-2 rounded-md px-2.5 py-1.5">
          <code className="text-muted-foreground min-w-0 flex-1 truncate font-mono text-[12px]">
            [
            {chunk.embedding
              .slice(0, VECTOR_PREVIEW)
              .map((v) => v.toFixed(4))
              .join(', ')}
            , … {chunk.embedding.length} values]
          </code>
          <CopyButton value={JSON.stringify(chunk.embedding)} label="Copy vector" />
        </div>
      )}
    </article>
  )
}

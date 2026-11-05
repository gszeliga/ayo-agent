import { FileText, Upload, X } from 'lucide-react'
import { useId, useRef, useState, type DragEvent } from 'react'

import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Drag a file in, or click (or press Enter) to pick one. */
export function FileDrop({
  file,
  onFile,
  error,
  disabled,
}: {
  file: File | null
  onFile: (file: File | null) => void
  error?: string
  disabled?: boolean
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const ids = { input: useId(), error: useId() }

  function drop(event: DragEvent) {
    event.preventDefault()
    setOver(false)
    if (disabled) return
    const dropped = event.dataTransfer.files[0]
    if (dropped) onFile(dropped)
  }

  return (
    <div className="space-y-1.5">
      <label htmlFor={ids.input} className="text-sm font-medium">
        Markdown file
      </label>
      <input
        ref={input}
        id={ids.input}
        type="file"
        accept=".md,text/markdown"
        className="sr-only"
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? ids.error : undefined}
        onChange={(event) => {
          onFile(event.target.files?.[0] ?? null)
          event.target.value = '' // picking the same file again still fires onChange
        }}
      />
      {file ? (
        <div className="bg-secondary flex items-center gap-3 rounded-lg px-3 py-2.5">
          <FileText aria-hidden="true" className="text-muted-foreground size-5 flex-none" />
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{file.name}</div>
            <div className="text-muted-foreground text-xs">{formatBytes(file.size)}</div>
          </div>
          <button
            type="button"
            aria-label="Remove file"
            disabled={disabled}
            className="text-muted-foreground hover:bg-accent rounded-sm p-1"
            onClick={() => {
              onFile(null)
            }}
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'bg-secondary text-muted-foreground flex w-full flex-col items-center gap-1.5 rounded-lg border-[1.5px] border-dashed border-input px-4 py-6',
            over && 'border-primary text-foreground',
            error && 'border-destructive',
          )}
          onClick={() => input.current?.click()}
          onDragOver={(event) => {
            event.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => {
            setOver(false)
          }}
          onDrop={drop}
        >
          <Upload aria-hidden="true" className="size-5" />
          <span>
            <span className="text-foreground font-medium">Choose a file</span> or drop it here
          </span>
          <span className="text-xs">Markdown (.md), UTF-8</span>
        </button>
      )}
      {error && (
        <p id={ids.error} className="text-destructive text-[13px]">
          {error}
        </p>
      )}
    </div>
  )
}

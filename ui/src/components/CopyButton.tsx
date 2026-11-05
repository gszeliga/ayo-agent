import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'

const FEEDBACK_MS = 1500

type Outcome = 'idle' | 'copied' | 'unavailable'

/**
 * Copies `value`. The clipboard API exists only in secure contexts (HTTPS, localhost); on
 * plain HTTP elsewhere it says so instead of failing silently.
 */
export function CopyButton({
  value,
  label,
  className,
}: {
  value: string
  /** What is copied, for screen readers: "Copy doc_id". */
  label: string
  className?: string
}) {
  const [outcome, setOutcome] = useState<Outcome>('idle')

  useEffect(() => {
    if (outcome === 'idle') return
    const timer = setTimeout(() => {
      setOutcome('idle')
    }, FEEDBACK_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [outcome])

  async function copy() {
    try {
      // Absent outside secure contexts, whatever the DOM types say.
      const clipboard = navigator.clipboard as Clipboard | undefined
      if (!clipboard) throw new Error('no clipboard')
      await clipboard.writeText(value)
      setOutcome('copied')
    } catch {
      setOutcome('unavailable')
    }
  }

  const text = { idle: label, copied: 'Copied', unavailable: 'Copy unavailable' }[outcome]
  return (
    <button
      type="button"
      title={text}
      aria-label={text}
      className={cn(
        'text-muted-foreground hover:bg-accent hover:text-foreground inline-flex size-7 flex-none items-center justify-center rounded-sm',
        outcome === 'unavailable' && 'text-destructive',
        className,
      )}
      onClick={() => void copy()}
    >
      {outcome === 'copied' ? (
        <Check aria-hidden="true" className="text-success size-4" />
      ) : (
        <Copy aria-hidden="true" className="size-4" />
      )}
      <span role="status" className="sr-only">
        {outcome === 'idle' ? '' : text}
      </span>
    </button>
  )
}

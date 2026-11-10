import { SlidersHorizontal } from 'lucide-react'
import { useId } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Field } from '@/upload/Field'

/** The less common options: a minimum similarity and the documents of other models. */
export function SearchOptionsPopover({
  open,
  onOpenChange,
  minSimilarity,
  onMinSimilarity,
  minError,
  includeOutdated,
  onIncludeOutdated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** As typed. */
  minSimilarity: string
  onMinSimilarity: (text: string) => void
  minError?: string
  includeOutdated: boolean
  onIncludeOutdated: (include: boolean) => void
}) {
  const outdatedId = useId()
  const set = (minSimilarity.trim() ? 1 : 0) + (includeOutdated ? 1 : 0)
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" aria-invalid={minError ? true : undefined}>
          <SlidersHorizontal aria-hidden="true" />
          Options
          {set > 0 && (
            <span className="bg-secondary text-muted-foreground rounded-sm px-1.5 text-[11px] font-semibold">
              {set}
              <span className="sr-only"> set</span>
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" aria-label="Search options" className="w-84 space-y-4">
        <Field
          label="Minimum similarity"
          error={minError}
          hint="0 to 1. Chunks below it are dropped from the top k. Empty keeps them all."
        >
          {(props) => (
            <Input
              {...props}
              inputMode="decimal"
              autoComplete="off"
              placeholder="None"
              className="w-32 tabular-nums"
              value={minSimilarity}
              onChange={(event) => {
                onMinSimilarity(event.target.value)
              }}
            />
          )}
        </Field>
        <div className="flex items-start gap-2.5">
          <Checkbox
            id={outdatedId}
            className="mt-0.5"
            checked={includeOutdated}
            onCheckedChange={(state) => {
              onIncludeOutdated(state === true)
            }}
          />
          <label htmlFor={outdatedId} className="cursor-pointer text-sm">
            <span className="font-medium">Include documents embedded with another model</span>
            <span className="text-muted-foreground block text-[13px]">
              Their vectors live in another space, so their similarity means little. They are
              flagged in the results.
            </span>
          </label>
        </div>
      </PopoverContent>
    </Popover>
  )
}

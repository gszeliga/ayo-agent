import { SlidersHorizontal } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'

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
  const { t } = useTranslation('search')
  const outdatedId = useId()
  const set = (minSimilarity.trim() ? 1 : 0) + (includeOutdated ? 1 : 0)
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          aria-invalid={minError ? true : undefined}
          // With options set, the name says how many: "Options, 1 set". The badge alone would
          // run into the word ("Options1 set"), as names are joined without spaces.
          aria-label={set > 0 ? t('options.buttonSet', { count: set }) : undefined}
        >
          <SlidersHorizontal aria-hidden="true" />
          {t('options.button')}
          {set > 0 && (
            <span
              aria-hidden="true"
              className="bg-secondary text-muted-foreground rounded-sm px-1.5 text-[11px] font-semibold"
            >
              {set}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" aria-label={t('options.label')} className="w-84 space-y-4">
        <Field label={t('options.min')} error={minError} hint={t('options.minHint')}>
          {(props) => (
            <Input
              {...props}
              inputMode="decimal"
              autoComplete="off"
              placeholder={t('options.minPlaceholder')}
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
            <span className="font-medium">{t('options.outdated')}</span>
            <span className="text-muted-foreground block text-[13px]">
              {t('options.outdatedHint')}
            </span>
          </label>
        </div>
      </PopoverContent>
    </Popover>
  )
}

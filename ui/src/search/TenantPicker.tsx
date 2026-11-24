import { ChevronDown } from 'lucide-react'
import { useId } from 'react'
import { Trans, useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useTenants } from '@/documents/queries'
import { useLanguage } from '@/layout/languageContext'
import { cn } from '@/lib/utils'

import { tenantsSummary } from './format'
import { MAX_TENANTS } from './searchParams'

/** A multi-select of the tenants (`GET /admin/tenants`, with their counts); none = all. */
export function TenantPicker({
  value,
  onChange,
}: {
  value: string[]
  onChange: (tenants: string[]) => void
}) {
  const { t } = useTranslation('search')
  const { language } = useLanguage()
  const labelId = useId()
  const valueId = useId()
  const tenants = useTenants()
  const known = tenants.data ?? []
  // Tenants from the URL that have no documents (any more) stay listed, so they can be unticked.
  const names = [...new Set([...known.map((t) => t.tenant), ...value])].sort()
  const counts = new Map(known.map((t) => [t.tenant, t]))

  function toggle(tenant: string, checked: boolean) {
    const next = checked ? [...value, tenant] : value.filter((t) => t !== tenant)
    onChange([...new Set(next)].sort())
  }

  return (
    <div className="space-y-1.5">
      <div id={labelId} className="text-sm leading-none font-medium">
        {t('tenants.label')}
      </div>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            aria-labelledby={`${labelId} ${valueId}`}
            className="min-w-52 justify-between"
          >
            <span id={valueId}>{tenantsSummary(value, language)}</span>
            <ChevronDown aria-hidden="true" className="text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" aria-label={t('tenants.popover')} className="w-80 p-1.5">
          <button
            type="button"
            aria-pressed={value.length === 0}
            className={cn(
              'hover:bg-accent flex min-h-8 w-full items-center justify-between rounded-sm px-2 text-left text-[13px]',
              value.length === 0 && 'text-primary font-semibold',
            )}
            onClick={() => {
              onChange([])
            }}
          >
            {t('tenants.all')}
          </button>
          <div className="bg-border my-1 h-px" />
          {tenants.isPending && (
            <p className="text-muted-foreground px-2 py-1.5 text-[13px]">{t('tenants.loading')}</p>
          )}
          {tenants.isError && (
            <p className="text-destructive px-2 py-1.5 text-[13px]">{t('tenants.failed')}</p>
          )}
          {tenants.isSuccess && names.length === 0 && (
            <p className="text-muted-foreground px-2 py-1.5 text-[13px]">{t('tenants.none')}</p>
          )}
          <ul className="max-h-64 overflow-y-auto">
            {names.map((tenant) => {
              const count = counts.get(tenant)
              const checked = value.includes(tenant)
              return (
                <li key={tenant}>
                  <label className="hover:bg-accent flex min-h-8 cursor-pointer items-center gap-2 rounded-sm px-2 text-[13px]">
                    <Checkbox
                      checked={checked}
                      disabled={!checked && value.length >= MAX_TENANTS}
                      onCheckedChange={(state) => {
                        toggle(tenant, state === true)
                      }}
                    />
                    <span className="flex-1 font-mono">{tenant}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {count
                        ? t('tenants.counts', {
                            docs: count.document_count,
                            chunks: count.chunk_count,
                          })
                        : t('tenants.noDocuments')}
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
          <p className="text-muted-foreground border-t px-2 pt-2 pb-1 text-[12px]">
            <Trans
              t={t}
              i18nKey="tenants.note"
              components={{ mono: <span className="font-mono" /> }}
            />
          </p>
        </PopoverContent>
      </Popover>
    </div>
  )
}

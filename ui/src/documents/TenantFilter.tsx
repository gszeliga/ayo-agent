import { Link, useNavigate } from 'react-router'

import type { components } from '@/api/schema'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { toSearchParams, type ListParams } from './listParams'

type TenantSummary = components['schemas']['TenantSummary']

interface Entry {
  tenant: string | null
  label: string
  count: number
}

/** "All tenants", each tenant, and the selected one even when it has no documents (any more). */
function entries(tenants: TenantSummary[], selected: string | null): Entry[] {
  const list: Entry[] = [
    {
      tenant: null,
      label: 'All tenants',
      count: tenants.reduce((sum, t) => sum + t.document_count, 0),
    },
    ...tenants.map((t) => ({ tenant: t.tenant, label: t.tenant, count: t.document_count })),
  ]
  if (selected !== null && !tenants.some((t) => t.tenant === selected)) {
    list.push({ tenant: selected, label: selected, count: 0 })
  }
  return list
}

function href(params: ListParams, tenant: string | null): string {
  const search = toSearchParams({ ...params, tenant, page: 1 }).toString()
  return search ? `?${search}` : '?'
}

interface Props {
  tenants: TenantSummary[] | undefined
  params: ListParams
}

/** The tenants as a sidebar, on wide screens (TenantSelect replaces it on narrow ones). */
export function TenantSidebar({ tenants, params }: Props) {
  if (tenants === undefined) {
    return (
      <div className="hidden w-56 flex-none space-y-2 lg:block" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-8" />
        ))}
      </div>
    )
  }
  return (
    <nav aria-label="Tenants" className="hidden w-56 flex-none lg:block">
      <h2 className="text-muted-foreground mb-2 px-2.5 text-xs font-semibold uppercase">Tenants</h2>
      <ul className="space-y-0.5">
        {entries(tenants, params.tenant).map((entry) => {
          const current = entry.tenant === params.tenant
          return (
            <li key={entry.tenant ?? ''}>
              <Link
                to={href(params, entry.tenant)}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  'hover:bg-accent flex min-h-9 items-center justify-between rounded-md px-2.5',
                  current && 'bg-secondary font-medium',
                )}
              >
                <span className="truncate">{entry.label}</span>
                <span className="text-muted-foreground text-xs tabular-nums">{entry.count}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

/** The tenants as a select in the toolbar, below the sidebar's breakpoint. */
export function TenantSelect({ tenants, params }: Props) {
  const navigate = useNavigate()
  if (tenants === undefined) return null
  return (
    <div className="lg:hidden">
      <label htmlFor="tenant-select" className="sr-only">
        Tenant
      </label>
      <select
        id="tenant-select"
        className="border-input bg-card h-9 rounded-md border px-3"
        value={params.tenant ?? ''}
        onChange={(event) => {
          void navigate(href(params, event.target.value || null))
        }}
      >
        {entries(tenants, params.tenant).map((entry) => (
          <option key={entry.tenant ?? ''} value={entry.tenant ?? ''}>
            {entry.label} ({entry.count})
          </option>
        ))}
      </select>
    </div>
  )
}

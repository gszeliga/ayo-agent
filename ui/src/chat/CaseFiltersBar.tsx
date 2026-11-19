import { Search } from 'lucide-react'

import type { components } from '@/api/schema'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

import { PHASE_LABELS, PHASES, type Phase } from './phases'
import { CASE_SEARCH_MAX_LENGTH, type CaseFilters, type CaseState } from './queries'

type TenantSummary = components['schemas']['TenantSummary']

const STATES: { value: CaseState; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'closed', label: 'Closed' },
]

const SELECT = 'border-input bg-card h-9 min-w-0 flex-1 rounded-md border px-2'

/**
 * The tenants offered: those `/admin/tenants` knows (tenants with documents), plus the
 * selected one, so a choice never disappears from its own select.
 */
function tenantOptions(tenants: TenantSummary[] | undefined, selected: string | null): string[] {
  const names = (tenants ?? []).map((t) => t.tenant)
  if (selected !== null && !names.includes(selected)) names.push(selected)
  return names
}

interface Props {
  filters: CaseFilters
  tenants: TenantSummary[] | undefined
  onChange: (filters: CaseFilters) => void
}

/** Search, tenant, phase and open/closed. The caller debounces the search. */
export function CaseFiltersBar({ filters, tenants, onChange }: Props) {
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search
          aria-hidden="true"
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
        />
        <Input
          type="search"
          aria-label="Search cases"
          placeholder="Search what happens"
          className="pl-8"
          maxLength={CASE_SEARCH_MAX_LENGTH}
          value={filters.q}
          onChange={(event) => {
            onChange({ ...filters, q: event.target.value })
          }}
        />
      </div>
      <div className="flex gap-2">
        <select
          aria-label="Tenant"
          className={SELECT}
          value={filters.tenant ?? ''}
          onChange={(event) => {
            onChange({ ...filters, tenant: event.target.value || null })
          }}
        >
          <option value="">All tenants</option>
          {tenantOptions(tenants, filters.tenant).map((tenant) => (
            <option key={tenant} value={tenant}>
              {tenant}
            </option>
          ))}
        </select>
        <select
          aria-label="Phase"
          className={SELECT}
          value={filters.phase ?? ''}
          onChange={(event) => {
            onChange({ ...filters, phase: (event.target.value || null) as Phase | null })
          }}
        >
          <option value="">All phases</option>
          {PHASES.map((phase) => (
            <option key={phase} value={phase}>
              {PHASE_LABELS[phase]}
            </option>
          ))}
        </select>
      </div>
      <div role="group" aria-label="State" className="bg-muted flex rounded-md p-0.5">
        {STATES.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={filters.state === value}
            className={cn(
              'text-muted-foreground flex-1 rounded-sm px-2 py-1 text-[13px] font-medium',
              filters.state === value && 'bg-card text-foreground shadow-xs',
            )}
            onClick={() => {
              onChange({ ...filters, state: value })
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { useTenants } from '@/documents/queries'

import { loadLastTenant } from './lastTenant'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStart: (tenant: string) => void
}

/** Asks for the tenant of a new conversation; the last one used is preselected. */
export function NewConversationDialog({ open, onOpenChange, onStart }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* Mounted per opening, so the choice starts from the last tenant each time. */}
        {open && (
          <TenantForm
            onStart={onStart}
            onCancel={() => {
              onOpenChange(false)
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function TenantForm({
  onStart,
  onCancel,
}: {
  onStart: (tenant: string) => void
  onCancel: () => void
}) {
  const tenants = useTenants()
  const names = tenants.data?.map((t) => t.tenant) ?? []
  const last = loadLastTenant()
  const [chosen, setChosen] = useState<string | null>(null)
  const tenant = chosen ?? (last !== null && names.includes(last) ? last : (names[0] ?? ''))

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (tenant) onStart(tenant)
      }}
    >
      <DialogHeader>
        <DialogTitle>New conversation</DialogTitle>
        <DialogDescription>
          The case is created by the first message, for this tenant.
        </DialogDescription>
      </DialogHeader>
      {tenants.isPending ? (
        <p className="text-muted-foreground">Loading tenants…</p>
      ) : tenants.isError ? (
        <p role="alert" className="text-destructive">
          The tenants could not be loaded.
        </p>
      ) : names.length === 0 ? (
        <p className="text-muted-foreground">
          No tenants yet: a tenant appears once it has a document.
        </p>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="new-conversation-tenant">Tenant</Label>
          <select
            id="new-conversation-tenant"
            className="border-input bg-card h-9 w-full rounded-md border px-3"
            value={tenant}
            onChange={(event) => {
              setChosen(event.target.value)
            }}
          >
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
      )}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!tenant}>
          Start
        </Button>
      </DialogFooter>
    </form>
  )
}

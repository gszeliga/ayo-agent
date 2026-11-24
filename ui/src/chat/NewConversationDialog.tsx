import { useState } from 'react'
import { useTranslation } from 'react-i18next'

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
  const { t } = useTranslation('chat')
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
        <DialogTitle>{t('newConversation.title')}</DialogTitle>
        <DialogDescription>{t('newConversation.description')}</DialogDescription>
      </DialogHeader>
      {tenants.isPending ? (
        <p className="text-muted-foreground">{t('newConversation.loadingTenants')}</p>
      ) : tenants.isError ? (
        <p role="alert" className="text-destructive">
          {t('newConversation.tenantsFailed')}
        </p>
      ) : names.length === 0 ? (
        <p className="text-muted-foreground">{t('newConversation.noTenants')}</p>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="new-conversation-tenant">{t('newConversation.tenant')}</Label>
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
          {t('newConversation.cancel')}
        </Button>
        <Button type="submit" disabled={!tenant}>
          {t('newConversation.start')}
        </Button>
      </DialogFooter>
    </form>
  )
}

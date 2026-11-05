import { LogOut, ShieldAlert, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router'

import { Button } from '@/components/ui/button'
import { useConnection } from '@/connection/context'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/paths'

import { dismissBanner, isBannerDismissed } from './banner'

const NAV = [
  { to: ROUTES.documents, label: 'Documents' },
  { to: ROUTES.settings, label: 'Indexing settings' },
]

export function AppShell() {
  const { connection, disconnect } = useConnection()
  const [bannerVisible, setBannerVisible] = useState(() => !isBannerDismissed())
  const host = connection ? new URL(connection.baseUrl).host : ''

  return (
    <div className="min-h-screen">
      {bannerVisible && (
        <div
          role="note"
          className="bg-warning-muted text-warning flex items-center gap-3 px-4 py-2 text-[13px]"
        >
          <ShieldAlert aria-hidden="true" className="size-4 flex-none" />
          <p className="flex-1">
            Internal use only: this UI sends the shared admin key from your browser.
          </p>
          <button
            type="button"
            aria-label="Dismiss"
            className="hover:bg-warning/10 rounded-sm p-1"
            onClick={() => {
              dismissBanner()
              setBannerVisible(false)
            }}
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
      )}
      <header className="bg-card border-b">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-3">
            <div
              aria-hidden="true"
              className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md text-[13px] font-bold"
            >
              AYO
            </div>
            <div className="leading-tight">
              <div className="font-semibold">AYO Admin</div>
              <div className="text-muted-foreground font-mono text-[12px]">{host}</div>
            </div>
          </div>
          <nav aria-label="Main" className="flex flex-1 gap-1">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'text-muted-foreground hover:bg-accent flex min-h-8 items-center rounded-md px-2.5 font-medium',
                    isActive && 'bg-secondary text-foreground',
                  )
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <Button
            variant="outline"
            onClick={() => {
              disconnect()
            }}
          >
            <LogOut aria-hidden="true" />
            Disconnect
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

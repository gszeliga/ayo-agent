import { LogOut, MessagesSquare, ShieldAlert, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation } from 'react-router'

import { Button } from '@/components/ui/button'
import { useConnection } from '@/connection/context'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/paths'

import { dismissBanner, isBannerDismissed } from './banner'
import { ErrorBoundary } from './ErrorBoundary'
import { LanguageToggle } from './LanguageToggle'
import { StatusIndicator } from './StatusIndicator'
import { ThemeToggle } from './ThemeToggle'

/** The knowledge base's pages, after the test chat (decision 21 in plans/chat-progress.md). */
const KNOWLEDGE_NAV = [
  { to: ROUTES.documents, label: 'shell.documents' },
  { to: ROUTES.search, label: 'shell.search' },
  { to: ROUTES.settings, label: 'shell.indexingSettings' },
] as const

export function AppShell() {
  const { t } = useTranslation()
  const { connection, disconnect } = useConnection()
  const { pathname } = useLocation()
  const [bannerVisible, setBannerVisible] = useState(() => !isBannerDismissed())
  const host = connection ? new URL(connection.baseUrl).host : ''
  // The test chat uses the whole window: three columns, each scrolling on its own.
  const fullWidth = pathname === ROUTES.chat || pathname.startsWith(`${ROUTES.chat}/`)

  return (
    <div className={cn('flex flex-col', fullWidth ? 'h-screen' : 'min-h-screen')}>
      <header className="bg-card border-b">
        {bannerVisible && (
          <div
            role="note"
            className="bg-warning-muted text-warning flex items-center gap-3 px-4 py-2 text-[13px]"
          >
            <ShieldAlert aria-hidden="true" className="size-4 flex-none" />
            <p className="flex-1">{t('shell.banner')}</p>
            <button
              type="button"
              aria-label={t('shell.dismiss')}
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
        {/* The full window width: the bar no longer fits the content's max-w-6xl. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
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
          <nav
            aria-label={t('shell.mainNav')}
            className="flex flex-1 items-center gap-1 whitespace-nowrap"
          >
            <NavLink
              to={ROUTES.chat}
              className={({ isActive }) =>
                cn(
                  'border-primary/40 text-primary hover:bg-primary/10 flex min-h-8 items-center gap-1.5 rounded-full border px-3 font-medium',
                  isActive && 'bg-primary text-primary-foreground hover:bg-primary/90',
                )
              }
            >
              <MessagesSquare aria-hidden="true" className="size-4" />
              {t('shell.testChat')}
            </NavLink>
            <span aria-hidden="true" className="bg-border mx-2 h-5 w-px" />
            <span
              id="nav-knowledge"
              className="text-muted-foreground mr-1 text-xs font-semibold uppercase"
            >
              {t('shell.knowledge')}
            </span>
            <div role="group" aria-labelledby="nav-knowledge" className="flex gap-1">
              {KNOWLEDGE_NAV.map(({ to, label }) => (
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
                  {t(label)}
                </NavLink>
              ))}
            </div>
          </nav>
          <StatusIndicator />
          <ThemeToggle />
          <LanguageToggle />
          <Button
            variant="outline"
            onClick={() => {
              disconnect()
            }}
          >
            <LogOut aria-hidden="true" />
            {t('shell.disconnect')}
          </Button>
        </div>
      </header>
      <main
        className={cn(
          fullWidth ? 'min-h-0 w-full flex-1 px-4 py-4' : 'mx-auto w-full max-w-6xl px-4 py-6',
        )}
      >
        <ErrorBoundary resetKey={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}

import {
  FileText,
  LogOut,
  MessagesSquare,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  X,
  type LucideIcon,
} from 'lucide-react'
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

/** The knowledge base's pages, after the test chat and a divider (plans/nav-progress.md). */
const KNOWLEDGE_NAV = [
  { to: ROUTES.documents, label: 'shell.documents', Icon: FileText },
  { to: ROUTES.search, label: 'shell.search', Icon: Search },
  { to: ROUTES.settings, label: 'shell.indexingSettings', Icon: SlidersHorizontal },
] as const

/**
 * A tab of the main nav: the whole bar's height, underlined when current (a document's page
 * marks Documents). Below `md` only the icon shows; the label stays for screen readers.
 */
function NavTab({ to, Icon, label }: { to: string; Icon: LucideIcon; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'text-muted-foreground hover:text-foreground focus-visible:ring-ring flex flex-none items-center gap-2 border-b-2 border-transparent px-3 font-medium whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-inset',
          isActive && 'border-primary text-foreground [&>svg]:text-primary font-semibold',
        )
      }
    >
      <Icon aria-hidden="true" className="size-4" />
      <span className="sr-only md:not-sr-only">{label}</span>
    </NavLink>
  )
}

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
        {/* One row, the full window width: brand, the tabs, the utilities (decision 1 in
            plans/nav-progress.md). Narrow, the tabs show only their icons and scroll. */}
        <div className="flex h-14 items-stretch gap-x-4 px-4">
          <div className="flex flex-none items-center gap-3">
            <div
              aria-hidden="true"
              className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md text-[13px] font-bold"
            >
              AYO
            </div>
            <div className="hidden leading-tight sm:block">
              {/* eslint-disable-next-line i18next/no-literal-string -- the brand (decision 5) */}
              <div className="font-semibold">AYO Admin</div>
              <div className="text-muted-foreground font-mono text-[12px]">{host}</div>
            </div>
          </div>
          <nav
            aria-label={t('shell.mainNav')}
            className="flex min-w-0 flex-1 items-stretch overflow-x-auto"
          >
            <NavTab to={ROUTES.chat} Icon={MessagesSquare} label={t('shell.testChat')} />
            <span aria-hidden="true" className="bg-border mx-1 my-auto h-5 w-px flex-none" />
            <div role="group" aria-label={t('shell.knowledgeBase')} className="flex items-stretch">
              {KNOWLEDGE_NAV.map(({ to, label, Icon }) => (
                <NavTab key={to} to={to} Icon={Icon} label={t(label)} />
              ))}
            </div>
          </nav>
          <div className="flex flex-none items-center gap-1">
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

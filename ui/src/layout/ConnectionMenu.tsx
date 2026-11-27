import { ChevronDown, LogOut, Server } from 'lucide-react'
import { Trans, useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useConnection } from '@/connection/context'

import { LanguageChoices } from './LanguageToggle'
import { ThemeChoices } from './ThemeChoices'

/**
 * The header's last button: the host it is connected to, and a menu with the theme, the
 * language and Disconnect (decision 2 in plans/nav-progress.md). Its name holds the host,
 * the text it shows.
 */
export function ConnectionMenu() {
  const { t } = useTranslation()
  const { connection, disconnect } = useConnection()
  const host = connection ? new URL(connection.baseUrl).host : ''
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" aria-label={t('shell.connectionMenu', { host })}>
          <Server aria-hidden="true" className="text-muted-foreground" />
          <span className="hidden font-mono text-[12px] font-normal sm:inline">{host}</span>
          <ChevronDown aria-hidden="true" className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
          <Trans
            i18nKey="shell.connectedTo"
            components={{ host: <span className="text-foreground font-mono">{host}</span> }}
          />
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <ThemeChoices />
        <DropdownMenuSeparator />
        <LanguageChoices />
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onSelect={() => {
            disconnect()
          }}
        >
          <LogOut aria-hidden="true" />
          {t('shell.disconnect')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ThemeChoice } from '@/lib/theme'

import { useTheme } from './themeContext'

const CHOICES: { value: ThemeChoice; Icon: typeof Sun }[] = [
  { value: 'light', Icon: Sun },
  { value: 'dark', Icon: Moon },
  { value: 'system', Icon: Monitor },
]

export function ThemeToggle() {
  const { t } = useTranslation()
  const { choice, theme, setChoice } = useTheme()
  const Shown = theme === 'dark' ? Moon : Sun
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('theme.trigger', { choice: t(`theme.current.${choice}`) })}
        >
          <Shown aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t('theme.label')}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={choice}
          onValueChange={(value) => {
            setChoice(value as ThemeChoice)
          }}
        >
          {CHOICES.map(({ value, Icon }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <Icon aria-hidden="true" />
              {t(`theme.choice.${value}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

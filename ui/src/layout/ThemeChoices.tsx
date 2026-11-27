import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from '@/components/ui/dropdown-menu'
import type { ThemeChoice } from '@/lib/theme'

import { useTheme } from './themeContext'

const CHOICES: { value: ThemeChoice; Icon: typeof Sun }[] = [
  { value: 'light', Icon: Sun },
  { value: 'dark', Icon: Moon },
  { value: 'system', Icon: Monitor },
]

/** Light, Dark or System as radio items, for a dropdown menu (the connection menu). */
export function ThemeChoices() {
  const { t } = useTranslation()
  const { choice, setChoice } = useTheme()
  return (
    <>
      <DropdownMenuLabel>{t('theme.label')}</DropdownMenuLabel>
      <DropdownMenuRadioGroup
        aria-label={t('theme.label')}
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
    </>
  )
}

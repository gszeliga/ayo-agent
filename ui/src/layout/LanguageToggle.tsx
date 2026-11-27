import { Languages } from 'lucide-react'
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
import { LANGUAGE_NAMES, LANGUAGES, type LanguageChoice } from '@/lib/language'

import { useLanguage } from './languageContext'

/** The languages and System as radio items, for a dropdown menu (this one and the connection menu). */
export function LanguageChoices() {
  const { t } = useTranslation()
  const { choice, setChoice } = useLanguage()
  return (
    <>
      <DropdownMenuLabel>{t('language.label')}</DropdownMenuLabel>
      <DropdownMenuRadioGroup
        aria-label={t('language.label')}
        value={choice}
        onValueChange={(value) => {
          setChoice(value as LanguageChoice)
        }}
      >
        {LANGUAGES.map((language) => (
          // Each name in its own language, marked so a screen reader says it right.
          <DropdownMenuRadioItem key={language} value={language} lang={language}>
            {LANGUAGE_NAMES[language]}
          </DropdownMenuRadioItem>
        ))}
        <DropdownMenuRadioItem value="system">{t('language.system')}</DropdownMenuRadioItem>
      </DropdownMenuRadioGroup>
    </>
  )
}

/** The connect page's language button (once connected, the connection menu has it). */
export function LanguageToggle() {
  const { t } = useTranslation()
  const { choice } = useLanguage()
  const current = choice === 'system' ? t('language.systemCurrent') : LANGUAGE_NAMES[choice]
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('language.trigger', { choice: current })}>
          <Languages aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <LanguageChoices />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

import { Eye, EyeOff, Info } from 'lucide-react'
import { useId, useState, type SubmitEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { createApiClient, unwrap } from '@/api/client'
import { ApiError, describeError } from '@/api/errors'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { defaultBaseUrl, normalizeBaseUrl } from '@/connection/baseUrl'
import { useConnection } from '@/connection/context'
import { safeNext } from '@/connection/next'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useLanguage } from '@/layout/languageContext'
import { LanguageToggle } from '@/layout/LanguageToggle'
import { isServerReachable, unreachableMessage } from '@/connection/reachability'

/** What went wrong, kept as codes and worded when shown: a language switch rewords it. */
interface FieldErrors {
  baseUrl?: 'invalid'
  apiKey?: 'missing' | 'rejected'
  form?:
    | { kind: 'noAnswer'; baseUrl: string; reachable: boolean }
    | { kind: 'error'; baseUrl: string; error: ApiError }
}

/** Tries the URL and key with the cheapest `/admin` call before keeping them. */
async function checkConnection(baseUrl: string, apiKey: string): Promise<FieldErrors> {
  try {
    await unwrap(createApiClient(baseUrl, apiKey).GET('/admin/tenants'))
    return {}
  } catch (error) {
    if (!(error instanceof ApiError)) throw error
    if (error.status === 401) return { apiKey: 'rejected' }
    if (error.isNetworkError) {
      return { form: { kind: 'noAnswer', baseUrl, reachable: await isServerReachable(baseUrl) } }
    }
    return { form: { kind: 'error', baseUrl, error } }
  }
}

export function ConnectPage() {
  const { t } = useTranslation('connect')
  const { language } = useLanguage()
  useDocumentTitle(t('pageTitle'))
  const { connection, connect, notice } = useConnection()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [baseUrl, setBaseUrl] = useState(() => defaultBaseUrl())
  // The default is right almost always (the page's origin, or the build's API address), so
  // the field stays closed behind Change until it is needed.
  const [editingAddress, setEditingAddress] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [checking, setChecking] = useState(false)
  const ids = { baseUrl: useId(), apiKey: useId(), baseUrlError: useId(), apiKeyError: useId() }

  if (connection !== null && !checking) return <Navigate to={next} replace />

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const url = normalizeBaseUrl(baseUrl)
    const key = apiKey.trim()
    const found: FieldErrors = {}
    if (url === null) found.baseUrl = 'invalid'
    if (!key) found.apiKey = 'missing'
    setErrors(found)
    if (url === null || !key) return

    setChecking(true)
    const problems = await checkConnection(url, key)
    setChecking(false)
    setErrors(problems)
    // Nothing answered: a wrong address is the likely cause, so show the field.
    if (problems.form?.kind === 'noAnswer') setEditingAddress(true)
    if (Object.keys(problems).length === 0) {
      connect({ baseUrl: url, apiKey: key })
      void navigate(next, { replace: true })
    }
  }

  const form = errors.form
  const formMessage =
    form === undefined
      ? null
      : form.kind === 'noAnswer'
        ? unreachableMessage(form.baseUrl, form.reachable, window.location.origin, language)
        : describeError(form.error, form.baseUrl, language)

  return (
    <main className="relative flex min-h-screen items-center justify-center p-4">
      {/* The shell's language menu shows only once connected; this screen comes first. */}
      <div className="absolute top-3 right-3">
        <LanguageToggle />
      </div>
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div
              aria-hidden="true"
              className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md text-[13px] font-bold"
            >
              AYO
            </div>
            <CardTitle>
              <h1 className="text-lg font-semibold">{t('title')}</h1>
            </CardTitle>
          </div>
          <CardDescription>{t('description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" noValidate onSubmit={(event) => void submit(event)}>
            {notice && (
              <Alert>
                <AlertDescription>{t(`notice.${notice}`)}</AlertDescription>
              </Alert>
            )}
            {editingAddress ? (
              <div className="space-y-1.5">
                <Label htmlFor={ids.baseUrl}>{t('address')}</Label>
                <Input
                  id={ids.baseUrl}
                  type="url"
                  autoComplete="url"
                  spellCheck={false}
                  className="font-mono"
                  value={baseUrl}
                  aria-invalid={errors.baseUrl ? true : undefined}
                  aria-describedby={errors.baseUrl ? ids.baseUrlError : undefined}
                  // Mounted by a click on Change, or after a failed check: the next thing to edit.
                  autoFocus
                  onChange={(event) => {
                    setBaseUrl(event.target.value)
                  }}
                />
                {errors.baseUrl && (
                  <p id={ids.baseUrlError} className="text-destructive text-[13px]">
                    {t('fieldError.address')}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-1.5">
                <p className="text-sm leading-none font-medium">{t('address')}</p>
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-mono text-sm">{baseUrl}</span>
                  <Button
                    type="button"
                    variant="link"
                    size="sm"
                    className="h-auto flex-none p-0"
                    aria-label={t('changeAddress')}
                    onClick={() => {
                      setEditingAddress(true)
                    }}
                  >
                    {t('change')}
                  </Button>
                </div>
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor={ids.apiKey}>{t('key')}</Label>
              <div className="relative">
                <Input
                  id={ids.apiKey}
                  type={showKey ? 'text' : 'password'}
                  autoComplete="off"
                  spellCheck={false}
                  className="pr-10 font-mono"
                  value={apiKey}
                  aria-invalid={errors.apiKey ? true : undefined}
                  aria-describedby={errors.apiKey ? ids.apiKeyError : undefined}
                  onChange={(event) => {
                    setApiKey(event.target.value)
                  }}
                />
                <button
                  type="button"
                  className="text-muted-foreground hover:bg-accent absolute top-1/2 right-1.5 -translate-y-1/2 rounded-sm p-1"
                  aria-label={showKey ? t('hideKey') : t('showKey')}
                  onClick={() => {
                    setShowKey((shown) => !shown)
                  }}
                >
                  {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {errors.apiKey && (
                <p id={ids.apiKeyError} className="text-destructive text-[13px]">
                  {errors.apiKey === 'missing'
                    ? t('fieldError.keyMissing')
                    : t('fieldError.keyRejected')}
                </p>
              )}
            </div>
            {formMessage !== null && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>{formMessage}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={checking}>
              {checking ? t('checking') : t('submit')}
            </Button>
            <p className="text-muted-foreground flex gap-2 text-[13px]">
              <Info aria-hidden="true" className="mt-0.5 size-4 flex-none" />
              {t('note')}
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}

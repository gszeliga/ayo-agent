import { Eye, EyeOff, Info } from 'lucide-react'
import { useId, useState, type SubmitEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { createApiClient, unwrap } from '@/api/client'
import { ApiError } from '@/api/errors'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { defaultBaseUrl, normalizeBaseUrl } from '@/connection/baseUrl'
import { useConnection } from '@/connection/context'
import { safeNext } from '@/connection/next'

interface FieldErrors {
  baseUrl?: string
  apiKey?: string
  form?: string
}

/** Tries the URL and key with the cheapest `/admin` call before keeping them. */
async function checkConnection(baseUrl: string, apiKey: string): Promise<FieldErrors> {
  try {
    await unwrap(createApiClient(baseUrl, apiKey).GET('/admin/tenants'))
    return {}
  } catch (error) {
    if (!(error instanceof ApiError)) throw error
    if (error.status === 401) return { apiKey: 'Key rejected.' }
    if (error.isNetworkError) {
      return {
        form:
          `Can't reach the API at ${baseUrl}. Check the URL, that the API is running, and` +
          ` that CORS_ALLOWED_ORIGINS includes ${window.location.origin}.`,
      }
    }
    return { form: error.message }
  }
}

export function ConnectPage() {
  const { connection, connect, notice } = useConnection()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [baseUrl, setBaseUrl] = useState(() => defaultBaseUrl())
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
    if (url === null)
      found.baseUrl = 'Enter an http(s) address without a path, like https://host:8000.'
    if (!key) found.apiKey = 'Enter the admin key.'
    setErrors(found)
    if (url === null || !key) return

    setChecking(true)
    const problems = await checkConnection(url, key)
    setChecking(false)
    setErrors(problems)
    if (Object.keys(problems).length === 0) {
      connect({ baseUrl: url, apiKey: key })
      void navigate(next, { replace: true })
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
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
              <h1 className="text-lg font-semibold">Connect to the AYO API</h1>
            </CardTitle>
          </div>
          <CardDescription>The admin API this UI manages documents through.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" noValidate onSubmit={(event) => void submit(event)}>
            {notice && (
              <Alert>
                <AlertDescription>{notice}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-1.5">
              <Label htmlFor={ids.baseUrl}>API address</Label>
              <Input
                id={ids.baseUrl}
                type="url"
                autoComplete="url"
                spellCheck={false}
                className="font-mono"
                value={baseUrl}
                aria-invalid={errors.baseUrl ? true : undefined}
                aria-describedby={errors.baseUrl ? ids.baseUrlError : undefined}
                onChange={(event) => {
                  setBaseUrl(event.target.value)
                }}
              />
              {errors.baseUrl && (
                <p id={ids.baseUrlError} className="text-destructive text-[13px]">
                  {errors.baseUrl}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.apiKey}>Admin key</Label>
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
                  aria-label={showKey ? 'Hide key' : 'Show key'}
                  onClick={() => {
                    setShowKey((shown) => !shown)
                  }}
                >
                  {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {errors.apiKey && (
                <p id={ids.apiKeyError} className="text-destructive text-[13px]">
                  {errors.apiKey}
                </p>
              )}
            </div>
            {errors.form && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={checking}>
              {checking ? 'Checking…' : 'Connect'}
            </Button>
            <p className="text-muted-foreground flex gap-2 text-[13px]">
              <Info aria-hidden="true" className="mt-0.5 size-4 flex-none" />
              Internal use only: the key is kept in this tab until you close it.
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}

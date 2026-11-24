import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import { useId, useRef, useState, type SubmitEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useConnection } from '@/connection/context'
import { useTenants } from '@/documents/queries'
import { useLanguage } from '@/layout/languageContext'
import { relativeTime } from '@/lib/format'
import { useCachedServiceHealth } from '@/settings/healthQuery'
import { useIndexingSettings } from '@/settings/queries'

import { Field } from './Field'
import { FileDrop } from './FileDrop'
import { useExistingDocument } from './useExistingDocument'
import { describeFormProblem, uploadProblems, useUpload, type UploadProblems } from './useUpload'
import {
  describeProblem,
  effectiveSourceKey,
  fileProblem,
  tenantProblem,
  type Problem,
} from './validation'

type Document = components['schemas']['Document']

export type UploadMode =
  | { kind: 'upload'; defaultTenant: string | null }
  /** Same tenant and source key: the API replaces the document's content. */
  | { kind: 'replace'; document: Document }

export function UploadDialog({
  mode,
  open,
  onOpenChange,
}: {
  mode: UploadMode
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Remounted on each open: a fresh form every time. */}
      {open && (
        <UploadForm
          mode={mode}
          onClose={() => {
            onOpenChange(false)
          }}
        />
      )}
    </Dialog>
  )
}

function UploadForm({ mode, onClose }: { mode: UploadMode; onClose: () => void }) {
  const { t } = useTranslation('upload')
  const { language } = useLanguage()
  const baseUrl = useConnection().connection?.baseUrl ?? ''
  const replacing = mode.kind === 'replace' ? mode.document : null
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const upload = useUpload()
  const maxBytes = useIndexingSettings().data?.uploads.max_upload_bytes
  const tenants = useTenants().data
  const embeddings = useCachedServiceHealth()?.embeddings

  const [file, setFile] = useState<File | null>(null)
  const [tenant, setTenant] = useState(
    replacing?.tenant ?? (mode.kind === 'upload' ? (mode.defaultTenant ?? '') : ''),
  )
  const [title, setTitle] = useState(replacing?.title ?? '')
  const [sourceKey, setSourceKey] = useState(replacing?.source_key ?? '')
  const [force, setForce] = useState(false)
  const [problems, setProblems] = useState<UploadProblems>({ fields: {} })
  const [tenantTouched, setTenantTouched] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const ids = { tenants: useId(), force: useId() }
  const busy = upload.isPending

  const existing = useExistingDocument(
    tenant.trim(),
    file ? effectiveSourceKey(sourceKey, file.name) : '',
    replacing === null && file !== null,
  )
  const liveTenantProblem = tenantTouched && tenant ? tenantProblem(tenant.trim()) : null
  const words = (problem: Problem | null | undefined) =>
    problem ? describeProblem(problem, language) : undefined

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const found: UploadProblems = { fields: {} }
    if (!file) found.fields.file = { code: 'fileMissing' }
    else {
      const problem = fileProblem(file, maxBytes)
      if (problem) found.fields.file = problem
    }
    const tenantFound = replacing ? null : tenantProblem(tenant.trim())
    if (tenantFound) found.fields.tenant = tenantFound
    setProblems(found)
    if (!file || Object.keys(found.fields).length > 0) return

    controller.current = new AbortController()
    const signal = controller.current.signal
    upload.mutate(
      { file, tenant: tenant.trim(), title, sourceKey, force, signal },
      {
        onSuccess: (result) => {
          const name = title.trim() || replacing?.title || file.name
          if (result.status === 'up_to_date') {
            toast.success(t('toast.upToDate'), { description: t('toast.upToDateHint') })
          } else {
            const chunks = t('toast.chunks', { count: result.chunk_count ?? 0 })
            toast.success(t(replacing ? 'toast.replaced' : 'toast.indexed', { name, chunks }))
          }
          onClose()
          if (!replacing) {
            void navigate(`/documents/${result.doc_id}`, {
              state: { listSearch: location.search || '?' },
            })
          }
        },
        onError: (error) => {
          setProblems(
            signal.aborted
              ? { fields: {}, form: { code: 'cancelled' } }
              : uploadProblems(error, maxBytes),
          )
          if (signal.aborted) void queryClient.invalidateQueries({ queryKey: ['documents'] })
        },
      },
    )
  }

  return (
    <DialogContent
      showCloseButton={!busy}
      // Nothing closes the dialog by accident while a request runs; Cancel says what it does.
      onEscapeKeyDown={(event) => {
        if (busy) event.preventDefault()
      }}
      onInteractOutside={(event) => {
        if (busy) event.preventDefault()
      }}
      className="sm:max-w-lg"
    >
      <DialogHeader>
        <DialogTitle>{replacing ? t('replaceTitle') : t('uploadTitle')}</DialogTitle>
        <DialogDescription>
          {replacing
            ? t('replaceDescription', { name: replacing.title ?? replacing.source_key })
            : t('uploadDescription')}
        </DialogDescription>
      </DialogHeader>
      <form noValidate className="space-y-4" onSubmit={submit}>
        {embeddings?.status === 'down' && (
          // A warning, not a block: the provider may be back by now.
          <Alert role="note" className="bg-warning-muted text-warning border-transparent">
            <AlertTriangle aria-hidden="true" />
            <AlertDescription className="text-warning">
              {embeddings.error
                ? t('providerDownWithError', { error: embeddings.error })
                : t('providerDown')}
            </AlertDescription>
          </Alert>
        )}
        <FileDrop
          file={file}
          onFile={(next) => {
            setFile(next)
            setProblems((current) => ({
              ...current,
              fields: { ...current.fields, file: undefined },
            }))
          }}
          error={words(problems.fields.file)}
          disabled={busy}
        />

        {replacing ? (
          <dl className="bg-secondary grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg px-3 py-2.5 text-[13px]">
            <dt className="text-muted-foreground">{t('tenant.label')}</dt>
            <dd>{replacing.tenant}</dd>
            <dt className="text-muted-foreground">{t('sourceKey.label')}</dt>
            <dd className="font-mono break-all">{replacing.source_key}</dd>
          </dl>
        ) : (
          <Field
            label={t('tenant.label')}
            hint={t('tenant.hint')}
            error={words(problems.fields.tenant ?? liveTenantProblem)}
          >
            {(props) => (
              <>
                <Input
                  {...props}
                  list={ids.tenants}
                  autoComplete="off"
                  spellCheck={false}
                  // eslint-disable-next-line i18next/no-literal-string -- an example tenant id
                  placeholder="planta-norte"
                  value={tenant}
                  disabled={busy}
                  onChange={(event) => {
                    setTenant(event.target.value)
                    setTenantTouched(true)
                    setProblems((current) => ({
                      ...current,
                      fields: { ...current.fields, tenant: undefined },
                    }))
                  }}
                />
                <datalist id={ids.tenants}>
                  {tenants?.map((t) => (
                    <option key={t.tenant} value={t.tenant} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
        )}

        <Field label={t('title.label')} error={words(problems.fields.title)}>
          {(props) => (
            <Input
              {...props}
              placeholder={t('title.placeholder')}
              value={title}
              disabled={busy}
              onChange={(event) => {
                setTitle(event.target.value)
              }}
            />
          )}
        </Field>

        <Collapsible
          open={advancedOpen || Boolean(problems.fields.source_key)}
          onOpenChange={setAdvancedOpen}
        >
          <CollapsibleTrigger className="text-muted-foreground hover:text-foreground group flex items-center gap-1 text-[13px] font-medium">
            <ChevronRight
              aria-hidden="true"
              className="size-4 transition-transform group-data-[state=open]:rotate-90"
            />
            {t('advanced')}
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 pt-3">
            {!replacing && (
              <Field
                label={t('sourceKey.label')}
                hint={t('sourceKey.hint')}
                error={words(problems.fields.source_key)}
              >
                {(props) => (
                  <Input
                    {...props}
                    className="font-mono"
                    spellCheck={false}
                    placeholder={file?.name ?? t('sourceKey.placeholder')}
                    value={sourceKey}
                    disabled={busy}
                    onChange={(event) => {
                      setSourceKey(event.target.value)
                    }}
                  />
                )}
              </Field>
            )}
            <div className="flex items-start gap-2">
              <Checkbox
                id={ids.force}
                checked={force}
                disabled={busy}
                onCheckedChange={(checked) => {
                  setForce(checked === true)
                }}
              />
              <label htmlFor={ids.force} className="text-[13px] leading-tight">
                <span className="font-medium">{t('force.label')}</span>
                <span className="text-muted-foreground block">{t('force.hint')}</span>
              </label>
            </div>
          </CollapsibleContent>
        </Collapsible>

        {existing && (
          <Alert role="status" className="bg-warning-muted text-warning border-transparent">
            <AlertTriangle aria-hidden="true" />
            <AlertDescription className="text-warning">
              {t('existing', {
                tenant: existing.tenant,
                name: existing.title ?? existing.source_key,
                when: relativeTime(existing.updated_at, language),
              })}
            </AlertDescription>
          </Alert>
        )}

        {problems.form && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>
              {describeFormProblem(problems.form, baseUrl, language)}
            </AlertDescription>
          </Alert>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              if (busy) controller.current?.abort()
              else onClose()
            }}
          >
            {t('cancel')}
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? t('busy') : replacing ? t('replace') : t('upload')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}

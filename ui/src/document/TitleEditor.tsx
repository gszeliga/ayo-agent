import { Pencil } from 'lucide-react'
import { useId, useState, type SubmitEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { ApiError, describeError } from '@/api/errors'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useConnection } from '@/connection/context'
import { useRename } from '@/documents/mutations'
import { useLanguage } from '@/layout/languageContext'

type Document = components['schemas']['Document']

/** The API's limits for a title (DocumentUpdate). */
export const TITLE_MAX_LENGTH = 200

/** What is wrong with the draft, worded when shown; `api` is the API's own message. */
type TitleProblem =
  { code: 'empty' | 'tooLong' } | { code: 'api'; message: string } | { code: 'error'; error: Error }

/** The title, editable in place: Enter saves, Esc cancels. Not optimistic. */
export function TitleEditor({ doc, onGone }: { doc: Document; onGone: () => void }) {
  const { t } = useTranslation('document')
  const { language } = useLanguage()
  const title = doc.title ?? doc.source_key
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(title)
  const [problem, setError] = useState<TitleProblem | null>(null)
  const rename = useRename(doc.doc_id)
  const { connection } = useConnection()
  const ids = { input: useId(), error: useId() }

  function start() {
    setDraft(title)
    setError(null)
    setEditing(true)
  }

  function save(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = draft.trim()
    if (!next) {
      setError({ code: 'empty' })
      return
    }
    if (next.length > TITLE_MAX_LENGTH) {
      setError({ code: 'tooLong' })
      return
    }
    if (next === doc.title) {
      setEditing(false)
      return
    }
    rename.mutate(next, {
      onSuccess: () => {
        setEditing(false)
        toast.success(t('rename.done'))
      },
      onError: (failure) => {
        if (failure instanceof ApiError && failure.status === 404) {
          onGone()
          return
        }
        const field = failure instanceof ApiError ? failure.fieldErrors().title : undefined
        setError(field ? { code: 'api', message: field } : { code: 'error', error: failure })
      },
    })
  }

  function words(found: TitleProblem): string {
    switch (found.code) {
      case 'empty':
        return t('rename.empty')
      case 'tooLong':
        return t('rename.tooLong', { max: TITLE_MAX_LENGTH })
      case 'api':
        return found.message
      case 'error':
        return describeError(found.error, connection?.baseUrl ?? '', language)
    }
  }
  const error = problem === null ? null : words(problem)

  if (!editing) {
    return (
      <div className="flex min-w-0 items-start gap-1">
        <h1 className="min-w-0 text-xl font-semibold break-words" onDoubleClick={start}>
          {title}
        </h1>
        <Button variant="ghost" size="icon" aria-label={t('rename.button')} onClick={start}>
          <Pencil aria-hidden="true" />
        </Button>
      </div>
    )
  }
  return (
    <form className="flex min-w-0 flex-1 flex-col gap-1.5" noValidate onSubmit={save}>
      <label htmlFor={ids.input} className="sr-only">
        {t('rename.label')}
      </label>
      <div className="flex flex-wrap gap-2">
        <Input
          id={ids.input}
          // The user just asked to edit it.
          autoFocus
          className="min-w-64 flex-1 text-base font-semibold"
          value={draft}
          disabled={rename.isPending}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? ids.error : undefined}
          onChange={(event) => {
            setDraft(event.target.value)
            setError(null)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setEditing(false)
          }}
        />
        <Button type="submit" disabled={rename.isPending}>
          {rename.isPending ? t('rename.saving') : t('rename.save')}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={rename.isPending}
          onClick={() => {
            setEditing(false)
          }}
        >
          {t('rename.cancel')}
        </Button>
      </div>
      {error && (
        <p id={ids.error} className="text-destructive text-[13px]">
          {error}
        </p>
      )}
    </form>
  )
}

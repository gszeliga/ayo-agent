import { useMutation, useQueryClient } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import { ApiError, describeError } from '@/api/errors'
import { useApiClient } from '@/connection/context'
import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

import type { Problem } from './validation'

export interface UploadInput {
  file: File
  tenant: string
  /** Empty: the API takes the first `# ` heading, else the file name. */
  title: string
  /** Empty: the file name. */
  sourceKey: string
  force: boolean
  signal: AbortSignal
}

export type UploadField = 'file' | 'tenant' | 'title' | 'source_key'

/** A problem with the whole upload, worded when shown (`describeFormProblem`). */
export type FormProblem =
  | { code: 'cancelled' | 'providerFailed' }
  | { code: 'api'; message: string }
  | { code: 'error'; error: Error }

export interface UploadProblems {
  fields: Partial<Record<UploadField, Problem>>
  form?: FormProblem
}

const FIELDS: readonly UploadField[] = ['file', 'tenant', 'title', 'source_key']

/** `POST /admin/documents` as multipart; refreshes what it changes. */
export function useUpload() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, tenant, title, sourceKey, force, signal }: UploadInput) =>
      unwrap(
        client.POST('/admin/documents', {
          body: {
            // The schema types the file as a string; the serializer sends the File itself.
            file: file as unknown as string,
            tenant,
            title: title.trim() || null,
            source_key: sourceKey.trim() || null,
            force,
          },
          bodySerializer: (body) => {
            const form = new FormData()
            form.append('file', file, file.name)
            form.append('tenant', body.tenant)
            if (body.title) form.append('title', body.title)
            if (body.source_key) form.append('source_key', body.source_key)
            if (body.force) form.append('force', 'true')
            return form
          },
          signal,
        }),
      ),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['documents'] }),
        queryClient.invalidateQueries({ queryKey: ['tenants'] }),
        queryClient.invalidateQueries({ queryKey: ['settings'] }),
        queryClient.invalidateQueries({ queryKey: ['document', result.doc_id] }),
      ])
    },
  })
}

/** Where each error goes: next to its field when it has one, else above the buttons. */
export function uploadProblems(error: Error, maxBytes: number | undefined): UploadProblems {
  if (!(error instanceof ApiError)) return { fields: {}, form: { code: 'error', error } }
  if (error.status === 413) return { fields: { file: { code: 'tooLarge', maxBytes } } }
  if (error.status === 502) return { fields: {}, form: { code: 'providerFailed' } }
  if (error.status === 422) {
    const byField = error.fieldErrors()
    const fields: UploadProblems['fields'] = {}
    for (const field of FIELDS) {
      const message = byField[field]
      if (message) fields[field] = { code: 'api', message }
    }
    const unplaced = error.items.filter((item) => {
      const field = item.loc.findLast((part): part is string => typeof part === 'string')
      return !FIELDS.includes(field as UploadField)
    })
    const message = unplaced[0]?.msg
    return { fields, form: message === undefined ? undefined : { code: 'api', message } }
  }
  return { fields: {}, form: { code: 'error', error } }
}

export function describeFormProblem(
  problem: FormProblem,
  baseUrl: string,
  language: Language,
): string {
  switch (problem.code) {
    case 'api':
      return problem.message
    case 'error':
      return describeError(problem.error, baseUrl, language)
    default:
      return i18n.getFixedT(language, 'upload')(`problem.${problem.code}`)
  }
}

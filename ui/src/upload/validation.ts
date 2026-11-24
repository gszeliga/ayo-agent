import { i18n } from '@/i18n'
import { formatBytes } from '@/lib/format'
import type { Language } from '@/lib/language'

import { TENANT_PATTERN } from '@/documents/listParams'

/**
 * What is wrong with a field, kept as a code and worded when shown (`describeProblem`), so a
 * language switch rewords it. `api` is the API's own message for that field, shown as is.
 */
export type Problem =
  | { code: 'fileMissing' | 'notMarkdown' | 'empty' | 'tenantMissing' | 'tenantInvalid' }
  | { code: 'tooLarge'; maxBytes: number | undefined }
  | { code: 'api'; message: string }

export function tenantProblem(tenant: string): Problem | null {
  if (!tenant) return { code: 'tenantMissing' }
  return TENANT_PATTERN.test(tenant) ? null : { code: 'tenantInvalid' }
}

/**
 * What the API would refuse before reading the content (its encoding and whether anything
 * is indexable are left to it). `maxBytes` is unknown when the settings could not be read;
 * the API's 413 still applies then.
 */
export function fileProblem(file: File, maxBytes: number | undefined): Problem | null {
  if (!file.name.toLowerCase().endsWith('.md')) return { code: 'notMarkdown' }
  if (file.size === 0) return { code: 'empty' }
  if (maxBytes !== undefined && file.size > maxBytes) return { code: 'tooLarge', maxBytes }
  return null
}

export function describeProblem(problem: Problem, language: Language): string {
  const t = i18n.getFixedT(language, 'upload')
  switch (problem.code) {
    case 'api':
      return problem.message
    case 'tooLarge':
      return problem.maxBytes === undefined
        ? t('problem.tooLargeUnknown')
        : t('problem.tooLarge', { limit: formatBytes(problem.maxBytes, language) })
    default:
      return t(`problem.${problem.code}`)
  }
}

/**
 * The `source_key` the API will use, as its `normalize_source_key` does: the given one or
 * the file name, NFC-normalized, reduced to its last path component, trimmed.
 */
export function effectiveSourceKey(sourceKey: string, fileName: string): string {
  const name = (sourceKey.trim() || fileName).normalize('NFC')
  return (name.split(/[/\\]/).at(-1) ?? '').trim()
}

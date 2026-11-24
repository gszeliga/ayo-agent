import type { components } from '@/api/schema'
import { i18n } from '@/i18n'
import { formatUtc } from '@/lib/format'
import type { Language } from '@/lib/language'

import { caseStatus, structuredSummary } from './structuredSummary'
import { usageLine } from './trace'

type CaseDetail = components['schemas']['CaseDetail']
type CaseTurn = components['schemas']['CaseTurn']

export type ExportFormat = 'markdown' | 'json'

/** A gap in the loaded turns, as an API offset range (`end` excluded). */
export interface TurnRange {
  start: number
  end: number
}

/**
 * The offsets of the turns not loaded yet, of `total`: turn N sits at offset N - 1. The
 * loaded turns are usually one run at the end (the latest pages), but any set works.
 */
export function missingRanges(loaded: readonly number[], total: number): TurnRange[] {
  const have = new Set(loaded)
  const ranges: TurnRange[] = []
  let start: number | null = null
  for (let offset = 0; offset < total; offset += 1) {
    const missing = !have.has(offset + 1)
    if (missing && start === null) start = offset
    if (!missing && start !== null) {
      ranges.push({ start, end: offset })
      start = null
    }
  }
  if (start !== null) ranges.push({ start, end: total })
  return ranges
}

/** `case-8d2e4b71-20261123.md`: an id prefix and the UTC date, never the title (content). */
export function exportFileName(detail: CaseDetail, format: ExportFormat, now: Date): string {
  const date = now.toISOString().slice(0, 10).replaceAll('-', '')
  return `case-${detail.case_id.slice(0, 8)}-${date}.${format === 'json' ? 'json' : 'md'}`
}

/** The inspector's data as JSON: the case as `get_case` gave it and every turn, in order. */
export function exportJson(detail: CaseDetail, turns: readonly CaseTurn[], now: Date): string {
  return `${JSON.stringify({ exported_at: now.toISOString(), case: detail, turns }, null, 2)}\n`
}

/**
 * The case as Markdown: header, structured summary, AI summary, then the conversation. Its
 * words in `language` (the UI's when exported); ids, content and UTC times as they are.
 */
export function exportMarkdown(
  detail: CaseDetail,
  turns: readonly CaseTurn[],
  now: Date,
  language: Language,
): string {
  const t = i18n.getFixedT(language, 'chat')
  const field = (label: string, value: string) => `- ${label}: ${value}`
  const channel =
    detail.web_session_id !== null
      ? t('exportFile.webSession', { id: `\`${detail.web_session_id}\`` })
      : t('exportFile.anotherChannel')
  const lines: string[] = [
    `# ${detail.title ?? t('untitled')}`,
    '',
    `_${t('exportFile.exported', { time: formatUtc(now.toISOString()) })}_`,
    '',
    field(t('exportFile.case'), `\`${detail.case_id}\``),
    field(t('exportFile.tenant'), detail.tenant),
    field(t('exportFile.phase'), caseStatus(detail, language)),
    field(t('exportFile.opened'), formatUtc(detail.created_at)),
    field(t('exportFile.updated'), formatUtc(detail.updated_at)),
    ...(detail.closed_at !== null
      ? [field(t('exportFile.closed'), formatUtc(detail.closed_at))]
      : []),
    field(t('exportFile.channel'), channel),
    field(t('exportFile.turns'), String(detail.turns)),
    field(t('exportFile.usage'), usageLine(detail.usage, language)),
    '',
    `## ${t('structured.title')}`,
  ]
  for (const section of structuredSummary(detail, language)) {
    lines.push('', `### ${section.title}`, '')
    if (section.items.length === 0) lines.push(`_${section.empty}_`)
    else lines.push(...section.items.map((item) => `- ${item.replaceAll('\n', ' ')}`))
  }
  lines.push('', `## ${t('totals.summary')}`, '')
  const summary = detail.summary
  if (summary === null) {
    lines.push(`_${t('exportFile.noSummary')}_`)
  } else {
    const meta = [
      summary.model,
      formatUtc(summary.generated_at),
      t('aiSummary.version', { n: summary.source_version }),
      ...(summary.stale ? [t('exportFile.stale')] : []),
      usageLine(summary.usage, language),
    ]
    lines.push(`_${meta.join(' · ')}_`, '', summary.content.trim())
  }
  lines.push('', `## ${t('conversation')}`)
  if (turns.length === 0) lines.push('', `_${t('exportFile.noTurns')}_`)
  for (const turn of turns) {
    const phase =
      turn.phase_before === turn.phase_after
        ? t(`phase.${turn.phase_after}`)
        : t('phaseChange', {
            from: t(`phase.${turn.phase_before}`),
            to: t(`phase.${turn.phase_after}`),
          })
    lines.push(
      '',
      `### ${t('turn.label', { n: turn.turn })} · ${phase} · ${formatUtc(turn.created_at)}`,
      '',
      `**${t('exportFile.user')}:**`,
      '',
      turn.user_message.content.trim(),
      '',
      `**${t('exportFile.copilot')}:**`,
      '',
      turn.reply.content.trim(),
    )
  }
  return `${lines.join('\n')}\n`
}

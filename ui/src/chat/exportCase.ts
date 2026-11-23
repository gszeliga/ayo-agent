import type { components } from '@/api/schema'
import { formatUtc } from '@/lib/format'

import { PHASE_LABELS } from './phases'
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

/** The case as Markdown: header, structured summary, AI summary, then the conversation. */
export function exportMarkdown(detail: CaseDetail, turns: readonly CaseTurn[], now: Date): string {
  const lines: string[] = [
    `# ${detail.title ?? 'Untitled case'}`,
    '',
    `_Exported ${formatUtc(now.toISOString())} from the AYO test chat._`,
    '',
    `- Case: \`${detail.case_id}\``,
    `- Tenant: ${detail.tenant}`,
    `- Phase: ${caseStatus(detail)}`,
    `- Opened: ${formatUtc(detail.created_at)}`,
    `- Updated: ${formatUtc(detail.updated_at)}`,
    ...(detail.closed_at !== null ? [`- Closed: ${formatUtc(detail.closed_at)}`] : []),
    `- Channel: ${detail.web_session_id !== null ? `web session \`${detail.web_session_id}\`` : 'another channel'}`,
    `- Turns: ${String(detail.turns)}`,
    `- Usage: ${usageLine(detail.usage)}`,
    '',
    '## Structured summary',
  ]
  for (const section of structuredSummary(detail)) {
    lines.push('', `### ${section.title}`, '')
    if (section.items.length === 0) lines.push(`_${section.empty}_`)
    else lines.push(...section.items.map((item) => `- ${item.replaceAll('\n', ' ')}`))
  }
  lines.push('', '## AI summary', '')
  const summary = detail.summary
  if (summary === null) {
    lines.push('_None_')
  } else {
    lines.push(
      `_${summary.model} · ${formatUtc(summary.generated_at)} · version ${String(summary.source_version)}${summary.stale ? ' · stale' : ''} · ${usageLine(summary.usage)}_`,
      '',
      summary.content.trim(),
    )
  }
  lines.push('', '## Conversation')
  if (turns.length === 0) lines.push('', '_No turns_')
  for (const turn of turns) {
    const phase =
      turn.phase_before === turn.phase_after
        ? PHASE_LABELS[turn.phase_after]
        : `${PHASE_LABELS[turn.phase_before]} → ${PHASE_LABELS[turn.phase_after]}`
    lines.push(
      '',
      `### Turn ${String(turn.turn)} · ${phase} · ${formatUtc(turn.created_at)}`,
      '',
      '**User:**',
      '',
      turn.user_message.content.trim(),
      '',
      '**Copilot:**',
      '',
      turn.reply.content.trim(),
    )
  }
  return `${lines.join('\n')}\n`
}

import type { components } from '@/api/schema'
import { i18n } from '@/i18n'
import type { Language } from '@/lib/language'

import { groupEvents } from './events'

type CaseDetail = components['schemas']['CaseDetail']

export interface SummarySection {
  title: string
  items: string[]
  /** Said when there are no items. */
  empty: string
}

const FACTS = ['what', 'where', 'since', 'standard'] as const

/**
 * The case as a structured summary, from `get_case` only (no model call): the problem's
 * facts, the cause, the hypotheses, the evidence and the actions. Plain text in
 * `language`, for the Summary tab and the Markdown export.
 */
export function structuredSummary(detail: CaseDetail, language: Language): SummarySection[] {
  const t = i18n.getFixedT(language, 'chat')
  const groups = groupEvents(detail.events)
  const facts = detail.fields
  const content = (events: { content: string }[]) => events.map((event) => event.content)
  return [
    {
      title: t('structured.problem'),
      items: FACTS.flatMap((key) => {
        const value = facts[key]
        return value !== null
          ? [t('structured.fact', { label: t(`state.fact.${key}`), value })]
          : []
      }),
      empty: t('structured.notDescribed'),
    },
    {
      title: t('state.groups.validated_cause'),
      items: content(groups.validated_cause),
      empty: t('structured.notValidated'),
    },
    {
      title: t('state.groups.hypothesis'),
      items: content(groups.hypothesis),
      empty: t('state.none'),
    },
    {
      title: t('state.groups.hypothesis_discarded'),
      items: content(groups.hypothesis_discarded),
      empty: t('structured.none'),
    },
    { title: t('state.groups.evidence'), items: content(groups.evidence), empty: t('state.none') },
    {
      title: t('actions.list'),
      items: detail.actions.map((action) =>
        t('structured.action', {
          description: action.description,
          owner: action.owner,
          due: action.due_date,
          status: t(
            `structured.actionStatus.${
              action.status === 'done' ? 'done' : action.overdue ? 'overdue' : 'pending'
            }`,
          ),
        }),
      ),
      empty: t('state.none'),
    },
  ]
}

/** "Analyse, open" / "Closed" ("Analizar, abierto" / "Cerrado"). */
export function caseStatus(detail: CaseDetail, language: Language): string {
  const t = i18n.getFixedT(language, 'chat')
  return detail.phase === 'closed'
    ? t('phase.closed')
    : t('structured.statusOpen', { phase: t(`phase.${detail.phase}`) })
}

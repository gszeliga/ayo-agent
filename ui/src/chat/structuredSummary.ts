import type { components } from '@/api/schema'

import { groupEvents } from './events'
import { PHASE_LABELS } from './phases'

type CaseDetail = components['schemas']['CaseDetail']

export interface SummarySection {
  title: string
  items: string[]
  /** Said when there are no items. */
  empty: string
}

/**
 * The case as a structured summary, from `get_case` only (no model call): the problem's
 * facts, the cause, the hypotheses, the evidence and the actions. Plain text, for the
 * Summary tab and the Markdown export.
 */
export function structuredSummary(detail: CaseDetail): SummarySection[] {
  const groups = groupEvents(detail.events)
  const facts = detail.fields
  const content = (events: { content: string }[]) => events.map((event) => event.content)
  return [
    {
      title: 'Problem',
      items: [
        ...(facts.what !== null ? [`What: ${facts.what}`] : []),
        ...(facts.where !== null ? [`Where: ${facts.where}`] : []),
        ...(facts.since !== null ? [`Since: ${facts.since}`] : []),
        ...(facts.standard !== null ? [`Standard: ${facts.standard}`] : []),
      ],
      empty: 'Not described yet',
    },
    {
      title: 'Validated cause',
      items: content(groups.validated_cause),
      empty: 'Not validated yet',
    },
    { title: 'Hypotheses', items: content(groups.hypothesis), empty: 'None yet' },
    {
      title: 'Discarded hypotheses',
      items: content(groups.hypothesis_discarded),
      empty: 'None',
    },
    { title: 'Evidence', items: content(groups.evidence), empty: 'None yet' },
    {
      title: 'Actions',
      items: detail.actions.map(
        (action) =>
          `${action.description} (${action.owner}, due ${action.due_date}, ${
            action.status === 'done' ? 'done' : action.overdue ? 'pending, overdue' : 'pending'
          })`,
      ),
      empty: 'None yet',
    },
  ]
}

/** "Analyse, open" / "Closed". */
export function caseStatus(detail: CaseDetail): string {
  return detail.phase === 'closed' ? 'Closed' : `${PHASE_LABELS[detail.phase]}, open`
}

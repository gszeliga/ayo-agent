import type { components } from '@/api/schema'
import { formatUtc } from '@/lib/format'

import { EVENT_GROUPS, groupEvents, type CaseEvent } from './events'
import { PHASE_LABELS } from './phases'

type CaseDetail = components['schemas']['CaseDetail']

const FACTS = [
  { key: 'what', label: 'What' },
  { key: 'where', label: 'Where' },
  { key: 'since', label: 'Since' },
  { key: 'standard', label: 'Standard' },
] as const

/**
 * The case record: the four facts, then the annotations by type. Everything is conversation
 * content, shown as plain text (never rendered as Markdown or HTML).
 */
export function StateTab({ detail }: { detail: CaseDetail }) {
  const groups = groupEvents(detail.events)
  return (
    <div className="space-y-5">
      <section aria-labelledby="state-facts" className="space-y-2">
        <h2 id="state-facts" className="text-sm font-semibold">
          Facts
        </h2>
        <dl className="space-y-2 text-sm">
          {FACTS.map(({ key, label }) => {
            const value = detail.fields[key]
            return (
              <div key={key}>
                <dt className="text-muted-foreground text-xs font-medium">{label}</dt>
                <dd className="break-words whitespace-pre-wrap">
                  {value ?? <span className="text-muted-foreground italic">Not recorded yet</span>}
                </dd>
              </div>
            )
          })}
        </dl>
      </section>
      {EVENT_GROUPS.map(({ type, title }) => (
        <EventGroup key={type} id={`state-${type}`} title={title} events={groups[type]}>
          {type === 'hypothesis_discarded' && (
            <p className="text-muted-foreground text-xs">
              A discard is recorded on its own: it is not linked to the hypothesis it rules out.
            </p>
          )}
        </EventGroup>
      ))}
    </div>
  )
}

interface GroupProps {
  id: string
  title: string
  events: CaseEvent[]
  children?: React.ReactNode
}

function EventGroup({ id, title, events, children }: GroupProps) {
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-sm font-semibold">
        {title} <span className="text-muted-foreground font-normal">({events.length})</span>
      </h2>
      {children}
      {events.length === 0 ? (
        <p className="text-muted-foreground text-sm italic">None yet</p>
      ) : (
        <ul className="space-y-2">
          {events.map((event) => (
            <li key={event.id} className="rounded-md border px-3 py-2 text-sm">
              <p className="break-words whitespace-pre-wrap">{event.content}</p>
              <p className="text-muted-foreground mt-1 text-xs">
                In {PHASE_LABELS[event.state_at_time]} ·{' '}
                <time dateTime={event.created_at}>{formatUtc(event.created_at)}</time>
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

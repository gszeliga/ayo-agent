import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { formatUtc } from '@/lib/format'

import { EVENT_GROUPS, groupEvents, type CaseEvent } from './events'

type CaseDetail = components['schemas']['CaseDetail']

// Labelled by key (`chat.state.fact`).
const FACTS = ['what', 'where', 'since', 'standard'] as const

/**
 * The case record: the four facts, then the annotations by type. Everything is conversation
 * content, shown as plain text (never rendered as Markdown or HTML).
 */
export function StateTab({ detail }: { detail: CaseDetail }) {
  const { t } = useTranslation('chat')
  const groups = groupEvents(detail.events)
  return (
    <div className="space-y-5">
      <section aria-labelledby="state-facts" className="space-y-2">
        <h2 id="state-facts" className="text-sm font-semibold">
          {t('state.facts')}
        </h2>
        <dl className="space-y-2 text-sm">
          {FACTS.map((key) => {
            const value = detail.fields[key]
            return (
              <div key={key}>
                <dt className="text-muted-foreground text-xs font-medium">
                  {t(`state.fact.${key}`)}
                </dt>
                <dd className="break-words whitespace-pre-wrap">
                  {value ?? (
                    <span className="text-muted-foreground italic">{t('state.notRecorded')}</span>
                  )}
                </dd>
              </div>
            )
          })}
        </dl>
      </section>
      {EVENT_GROUPS.map((type) => (
        <EventGroup
          key={type}
          id={`state-${type}`}
          title={t(`state.groups.${type}`)}
          events={groups[type]}
        >
          {type === 'hypothesis_discarded' && (
            <p className="text-muted-foreground text-xs">{t('state.discardNote')}</p>
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
  const { t } = useTranslation('chat')
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-sm font-semibold">
        {title} <span className="text-muted-foreground font-normal">({events.length})</span>
      </h2>
      {children}
      {events.length === 0 ? (
        <p className="text-muted-foreground text-sm italic">{t('state.none')}</p>
      ) : (
        <ul className="space-y-2">
          {events.map((event) => (
            <li key={event.id} className="rounded-md border px-3 py-2 text-sm">
              <p className="break-words whitespace-pre-wrap">{event.content}</p>
              <p className="text-muted-foreground mt-1 text-xs">
                {t('state.inPhase', { phase: t(`phase.${event.state_at_time}`) })} ·{' '}
                <time dateTime={event.created_at}>{formatUtc(event.created_at)}</time>
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

import { CASES, makeCaseDetail, makeTurn } from '@/test/fixtures/cases'

import { exportFileName, exportJson, exportMarkdown, missingRanges } from './exportCase'

const NOW = new Date('2026-11-23T10:15:00Z')

test.each([
  [[], 0, []],
  [[], 3, [{ start: 0, end: 3 }]],
  [[26, 27, 28, 29, 30], 30, [{ start: 0, end: 25 }]],
  [[1, 2, 3], 3, []],
  [
    [1, 2, 5],
    6,
    [
      { start: 2, end: 4 },
      { start: 5, end: 6 },
    ],
  ],
])('turns %j loaded of %i miss the offsets %j', (loaded, total, expected) => {
  expect(missingRanges(loaded, total)).toEqual(expected)
})

test('the file name has an id prefix and the date, never the title', () => {
  const detail = makeCaseDetail(CASES[0])
  expect(exportFileName(detail, 'markdown', NOW)).toBe('case-8d2e4b71-20261123.md')
  expect(exportFileName(detail, 'json', NOW)).toBe('case-8d2e4b71-20261123.json')
})

test('the Markdown export has the header, both summaries and every turn in order', () => {
  const detail = makeCaseDetail(CASES[0], {
    turns: 2,
    events: [
      {
        id: 1,
        event_type: 'validated_cause',
        content: 'Film de 60 µm',
        state_at_time: 'analyse',
        created_at: '2026-11-12T09:00:00Z',
      },
    ],
    summary: {
      content: '**Problema:** merma.',
      model: 'openai/gpt-5-mini',
      generated_at: '2026-11-12T10:00:00Z',
      source_version: 2,
      stale: true,
      usage: {
        llm_calls: 1,
        prompt_tokens: null,
        completion_tokens: null,
        total_tokens: 1900,
        cost: 0.0011,
      },
    },
  })
  const turns = [makeTurn(1, { phase: 'challenge', phaseAfter: 'analyse' }), makeTurn(2)]

  const markdown = exportMarkdown(detail, turns, NOW)

  expect(markdown).toMatch(/^# Merma del 4 % en el envasado de la línea 2\n/)
  expect(markdown).toContain('_Exported 2026-11-23 10:15 UTC from the AYO test chat._')
  expect(markdown).toContain(`- Case: \`${detail.case_id}\``)
  expect(markdown).toContain('- Phase: Analyse, open')
  expect(markdown).toContain(`- Channel: web session \`${detail.web_session_id ?? ''}\``)
  expect(markdown).toContain('### Validated cause\n\n- Film de 60 µm')
  expect(markdown).toContain('### Hypotheses\n\n_None yet_')
  expect(markdown).toContain('openai/gpt-5-mini · 2026-11-12 10:00 UTC · version 2 · stale')
  expect(markdown).toContain('**Problema:** merma.')
  expect(markdown).toContain(
    '### Turn 1 · Challenge → Analyse · 2026-11-12 09:01 UTC\n\n**User:**\n\nMensaje 1 del operario\n\n**Copilot:**\n\nRespuesta 1 del copiloto',
  )
  expect(markdown.indexOf('### Turn 1')).toBeLessThan(markdown.indexOf('### Turn 2'))
})

test('an untitled case from another channel, without summary or turns', () => {
  const detail = makeCaseDetail(CASES[0], { title: null, web_session_id: null, turns: 0 })
  const markdown = exportMarkdown(detail, [], NOW)
  expect(markdown).toMatch(/^# Untitled case\n/)
  expect(markdown).toContain('- Channel: another channel')
  expect(markdown).toContain('## AI summary\n\n_None_')
  expect(markdown).toContain('## Conversation\n\n_No turns_')
})

test('the JSON export is the case and its turns as the API gave them', () => {
  const detail = makeCaseDetail(CASES[0])
  const turns = [makeTurn(1), makeTurn(2)]
  expect(JSON.parse(exportJson(detail, turns, NOW))).toEqual({
    exported_at: '2026-11-23T10:15:00.000Z',
    case: detail,
    turns,
  })
})

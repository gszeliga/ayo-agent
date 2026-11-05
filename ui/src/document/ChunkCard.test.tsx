import { render, screen, within } from '@testing-library/react'

import type { components } from '@/api/schema'

import { ChunkCard } from './ChunkCard'

type Chunk = components['schemas']['Chunk']

function chunk(index: number, text: string): Chunk {
  return {
    chunk_index: index,
    heading: 'PRO-014 > 2. Valores',
    chunk_text: text,
    char_count: text.length,
    embedding: null,
  }
}

const TABLE =
  '| Equipo | Presión |\n|---|---|\n| Selladora A | 3,8 bar |\n\nAjustar `PRESION_MIN`, ver [norma](https://intranet.example/14).'
// The splitter cut a code block: the fence never closes in this chunk.
const CUT = 'Ejecutar:\n\n```sh\nselladora --set PRESION_MIN=3.8'

test('rendered, a chunk shows its table, inline code and link', async () => {
  render(<ChunkCard chunk={chunk(0, TABLE)} view="rendered" />)

  const card = screen.getByRole('article', { name: 'Chunk 0' })
  expect(await within(card).findByRole('table')).toHaveTextContent('Selladora A3,8 bar')
  expect(within(card).getByText('PRESION_MIN').tagName).toBe('CODE')
  expect(within(card).getByRole('link', { name: 'norma' })).toHaveAttribute('target', '_blank')
})

test('raw, the text is shown exactly as embedded', () => {
  render(<ChunkCard chunk={chunk(0, TABLE)} view="raw" />)

  const card = screen.getByRole('article', { name: 'Chunk 0' })
  expect(within(card).queryByRole('table')).toBeNull()
  expect(card.querySelector('p')?.textContent).toBe(TABLE)
})

test('a code block cut by the splitter stays inside its card', async () => {
  render(
    <>
      <ChunkCard chunk={chunk(0, CUT)} view="rendered" />
      <ChunkCard chunk={chunk(1, 'Después, **anotar** el valor.')} view="rendered" />
    </>,
  )

  const cut = screen.getByRole('article', { name: 'Chunk 0' })
  expect(await within(cut).findByText(/selladora --set/)).toHaveProperty('tagName', 'CODE')
  const next = screen.getByRole('article', { name: 'Chunk 1' })
  expect(await within(next).findByText('anotar')).toHaveProperty('tagName', 'STRONG')
  expect(next.querySelector('pre')).toBeNull()
})

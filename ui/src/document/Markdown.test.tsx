import { render, screen, within } from '@testing-library/react'

import { PROCEDURE_MD } from '@/test/fixtures/markdown'

import { Markdown } from './Markdown'

function renderProcedure() {
  return render(<Markdown source={PROCEDURE_MD} />)
}

test('headings and GFM tables render', () => {
  renderProcedure()

  expect(
    screen.getByRole('heading', { level: 1, name: 'PRO-014 Control de sellado' }),
  ).toBeInTheDocument()
  const table = screen.getByRole('table')
  expect(within(table).getAllByRole('row')).toHaveLength(3)
  expect(table).toHaveTextContent('Selladora B4,0 bar4,6 bar')
})

test('inline code and fenced blocks become code elements', () => {
  const { container } = renderProcedure()

  const inline = screen.getByText('PRESION_MIN')
  expect(inline.tagName).toBe('CODE')
  expect(inline.closest('pre')).toBeNull()
  const block = container.querySelector('pre > code.language-sh')
  expect(block).toHaveTextContent('selladora --set PRESION_MIN=3.8')
  // The backticks are Markdown syntax, never shown as text.
  expect(container.textContent).not.toContain('`')
})

test('links open in a new tab without access to this page', () => {
  renderProcedure()

  const link = screen.getByRole('link', { name: 'norma interna' })
  expect(link).toHaveAttribute('href', 'https://intranet.example/normas/14')
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
})

test('a javascript: link loses its target', () => {
  renderProcedure()

  const link = screen.getByText('enlace peligroso').closest('a')
  expect(link?.getAttribute('href') ?? '').not.toMatch(/javascript/i)
})

test('images are not loaded; their alt text shows', () => {
  const { container } = renderProcedure()

  expect(container.querySelector('img')).toBeNull()
  expect(screen.getByText('Image not shown: Esquema de la junta')).toBeInTheDocument()
})

test('raw HTML is never rendered', () => {
  const { container } = renderProcedure()

  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('b')).toBeNull()
  expect(container.querySelector('[onclick]')).toBeNull()
  expect((window as { __pwned?: boolean }).__pwned).toBeUndefined()
})

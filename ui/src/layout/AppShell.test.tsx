import { screen, within } from '@testing-library/react'

import { renderApp } from '@/test/render'

const nav = () => screen.getByRole('navigation', { name: 'Main' })
const current = () =>
  within(nav())
    .getAllByRole('link')
    .filter((link) => link.getAttribute('aria-current') === 'page')
    .map((link) => link.textContent)

test.each([
  ['/chat', 'Test chat'],
  ['/chat/new', 'Test chat'],
  ['/documents', 'Documents'],
  ['/documents/doc-123', 'Documents'],
  ['/search', 'Search'],
  ['/settings', 'Indexing settings'],
])('on %s only the %s tab is current', (path, tab) => {
  renderApp(path, { connected: true })

  expect(current()).toEqual([tab])
})

test('every tab has an icon and a name, and the knowledge pages are a named group', () => {
  renderApp('/documents', { connected: true })

  const links = within(nav()).getAllByRole('link')
  for (const link of links) expect(link.querySelector('svg')).not.toBeNull()
  const group = within(nav()).getByRole('group', { name: 'Knowledge base' })
  expect(
    within(group)
      .getAllByRole('link')
      .map((link) => link.textContent),
  ).toEqual(['Documents', 'Search', 'Indexing settings'])
})

test('the group is named in Spanish too', () => {
  renderApp('/documents', { connected: true, language: 'es' })

  expect(
    within(screen.getByRole('navigation', { name: 'Principal' })).getByRole('group', {
      name: 'Base de conocimiento',
    }),
  ).toBeInTheDocument()
})

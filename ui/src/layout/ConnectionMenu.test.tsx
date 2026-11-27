import { screen, within } from '@testing-library/react'

import { loadConnection } from '@/connection/storage'
import { openConnectionMenu, renderApp } from '@/test/render'

const trigger = () => screen.getByRole('button', { name: 'Connection and preferences: api.test' })

test('the trigger shows the host; the menu says where it is connected and what is chosen', async () => {
  const { user } = renderApp('/documents', { connected: true })

  expect(trigger()).toHaveTextContent('api.test')
  const menu = await openConnectionMenu(user)

  expect(menu).toHaveTextContent('Connected to api.test')
  const theme = within(menu).getByRole('group', { name: 'Theme' })
  expect(within(theme).getByRole('menuitemradio', { name: 'System' })).toBeChecked()
  const language = within(menu).getByRole('group', { name: 'Language' })
  expect(within(language).getByRole('menuitemradio', { name: 'System' })).toBeChecked()
  expect(within(menu).getByRole('menuitem', { name: 'Disconnect' })).toBeInTheDocument()
})

test('the header has no separate theme, language or Disconnect buttons', () => {
  renderApp('/documents', { connected: true })

  expect(screen.queryByRole('button', { name: /^Theme/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^Language/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Disconnect' })).not.toBeInTheDocument()
})

test('Disconnect returns to the connect screen', async () => {
  const { user } = renderApp('/settings', { connected: true })

  await openConnectionMenu(user)
  await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))

  expect(screen.getByRole('heading', { name: 'Connect to the AYO API' })).toBeInTheDocument()
  expect(loadConnection()).toBeNull()
})

test('Escape closes the menu and gives the focus back to the trigger', async () => {
  const { user } = renderApp('/documents', { connected: true })

  await openConnectionMenu(user)
  await user.keyboard('{Escape}')

  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  expect(trigger()).toHaveFocus()
})

test('in Spanish', async () => {
  const { user } = renderApp('/documents', { connected: true, language: 'es' })

  expect(screen.getByRole('button', { name: 'Conexión y preferencias: api.test' })).toBeVisible()
  const menu = await openConnectionMenu(user)

  expect(menu).toHaveTextContent('Conectado a api.test')
  expect(within(menu).getByRole('menuitem', { name: 'Desconectar' })).toBeInTheDocument()
})

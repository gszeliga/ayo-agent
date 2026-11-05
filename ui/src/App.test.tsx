import { render, screen } from '@testing-library/react'

import { App } from './App'

test('renders the placeholder', () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: 'AYO Admin' })).toBeInTheDocument()
})

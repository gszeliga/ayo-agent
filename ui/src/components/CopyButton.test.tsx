import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { CopyButton } from './CopyButton'

test('copies the value and confirms', async () => {
  const user = userEvent.setup() // installs a clipboard stub
  render(<CopyButton value="upload-1890b5dc5335" label="Copy doc_id" />)

  await user.click(screen.getByRole('button', { name: 'Copy doc_id' }))

  expect(await navigator.clipboard.readText()).toBe('upload-1890b5dc5335')
  expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Copied')
})

test('says so when the clipboard is not available (plain HTTP)', async () => {
  const user = userEvent.setup()
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  render(<CopyButton value="x" label="Copy doc_id" />)

  await user.click(screen.getByRole('button', { name: 'Copy doc_id' }))

  expect(screen.getByRole('button', { name: 'Copy unavailable' })).toBeInTheDocument()
})

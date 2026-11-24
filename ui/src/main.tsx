import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './index.css'
// Before the app: i18next is ready, in the right language, for the first render.
import './i18n'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'

const root = document.getElementById('root')
if (!root) throw new Error('index.html has no #root element')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

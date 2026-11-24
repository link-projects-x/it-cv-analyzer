import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { apiConfig } from './api'
import { AppFlow } from './upload/AppFlow'
import './styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing in index.html')

createRoot(root).render(
  <StrictMode>
    <AppFlow api={apiConfig.api} pollMs={apiConfig.pollMs} demo={apiConfig.demo} needsAccessCode={apiConfig.needsAccessCode} local={apiConfig.local} />
  </StrictMode>,
)

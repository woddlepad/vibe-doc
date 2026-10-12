import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/newsreader/opsz-italic.css'
import '@fontsource-variable/hanken-grotesk'
import '@fontsource-variable/cormorant-garamond'
import '@fontsource-variable/manrope'
import '@fontsource/libre-caslon-display'
import '@fontsource-variable/libre-franklin'
import '@fontsource/spectral/300.css'
import '@fontsource/spectral/400.css'
import '@fontsource/spectral/400-italic.css'
import '@fontsource-variable/work-sans'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

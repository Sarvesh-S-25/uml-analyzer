import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import { applyThemeChoice, readThemeChoice } from './lib/theme'

// Applied before the first render, not in an effect: setting it afterwards
// paints one frame in the wrong theme, which reads as a flash on every load.
applyThemeChoice(readThemeChoice())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

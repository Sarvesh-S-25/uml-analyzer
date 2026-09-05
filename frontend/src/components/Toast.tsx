import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

/** Replaces the previous `alert()` calls.
 *
 * `alert` blocks the main thread, cannot be styled or read by assistive tech in
 * context, and makes the UI impossible to drive from an automated test -- which
 * matters here, because reproducible runs are part of the point.
 */
export type ToastTone = 'info' | 'good' | 'warning' | 'critical'

interface Toast {
  id: number
  tone: ToastTone
  message: string
}

interface ToastApi {
  notify: (message: string, tone?: ToastTone) => void
}

const ToastContext = createContext<ToastApi>({ notify: () => undefined })

export function useToast(): ToastApi {
  return useContext(ToastContext)
}

const TONE_COLORS: Record<ToastTone, string> = {
  info: '#3987e5',
  good: '#0ca30c',
  warning: '#fab219',
  critical: '#d03b3b',
}

const TONE_GLYPHS: Record<ToastTone, string> = {
  info: 'i',
  good: '✓',
  warning: '!',
  critical: '✗',
}

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const notify = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = nextId++
      setToasts((current) => [...current, { id, tone, message }])
      window.setTimeout(() => dismiss(id), tone === 'critical' ? 9000 : 5000)
    },
    [dismiss],
  )

  const api = useMemo(() => ({ notify }), [notify])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-50 flex w-[min(26rem,calc(100vw-2rem))] flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="flex items-start gap-3 rounded-lg border bg-surface px-4 py-3 text-sm text-ink-2 shadow-lg"
            style={{ borderColor: `${TONE_COLORS[toast.tone]}66` }}
          >
            <span
              aria-hidden="true"
              className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-plane"
              style={{ background: TONE_COLORS[toast.tone] }}
            >
              {TONE_GLYPHS[toast.tone]}
            </span>
            <span className="min-w-0 flex-1 break-words">{toast.message}</span>
            <button
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss notification"
              className="shrink-0 text-muted hover:text-ink"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

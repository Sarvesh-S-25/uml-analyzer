import { useEffect, useId, useRef, useState } from 'react'
import type { ComponentPropsWithRef, ReactNode } from 'react'
import { statusStyle } from '../lib/theme'
import type { ThemeChoice } from '../lib/theme'

/* Shared primitives.
 *
 * Two rules run through all of them:
 *   - a status is never carried by colour alone; every status-bearing component
 *     takes a glyph and a word as well, and renders all three;
 *   - anything destructive asks in a real dialog, not `window.confirm`, which
 *     cannot be styled, cannot be read in context by a screen reader, and
 *     blocks the thread so an automated check cannot drive it.
 */

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = '',
  bodyClassName = '',
  dense = false,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  dense?: boolean
}) {
  return (
    <section
      className={`rounded-xl border border-hairline bg-surface shadow-[var(--shadow-card)] ${className}`}
    >
      {(title || actions) && (
        <header
          className={`flex items-start justify-between gap-4 border-b border-hairline ${
            dense ? 'px-4 py-3' : 'px-5 py-4'
          }`}
        >
          <div className="min-w-0">
            {title && <h2 className="text-md font-semibold text-ink">{title}</h2>}
            {/* Capped at a comfortable measure: a subtitle running the full
                width of a wide card is a paragraph nobody reads. */}
            {subtitle && (
              <p className="mt-1 max-w-[68ch] text-sm leading-relaxed text-muted">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
        </header>
      )}
      <div className={`${dense ? 'p-4' : 'p-5'} ${bodyClassName}`}>{children}</div>
    </section>
  )
}

type ButtonProps = ComponentPropsWithRef<'button'> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle'
  size?: 'sm' | 'md'
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  const styles: Record<string, string> = {
    primary: 'bg-series-1 text-white hover:brightness-110 active:brightness-95 border border-transparent',
    secondary: 'bg-surface text-ink border border-hairline hover:bg-surface-2',
    subtle: 'bg-surface-2 text-ink-2 border border-transparent hover:bg-surface-3 hover:text-ink',
    ghost: 'text-ink-2 border border-transparent hover:bg-surface-2 hover:text-ink',
    danger: 'text-critical border border-critical/40 hover:bg-critical-wash',
  }
  const sizes: Record<string, string> = {
    sm: 'px-2.5 py-1 text-xs gap-1.5',
    md: 'px-3 py-1.5 text-sm gap-2',
  }
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${styles[variant]} ${sizes[size]} ${className}`}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  )
}

export function IconButton({
  label,
  children,
  className = '',
  ...rest
}: ComponentPropsWithRef<'button'> & { label: string; children: ReactNode }) {
  return (
    <button
      {...rest}
      aria-label={label}
      title={label}
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted transition hover:bg-surface-3 hover:text-ink ${className}`}
    >
      {children}
    </button>
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  )
}

export function Input({ className = '', ...rest }: ComponentPropsWithRef<'input'>) {
  return (
    <input
      {...rest}
      className={`w-full rounded-lg border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-series-1 focus:outline-none ${className}`}
    />
  )
}

export function Select({ className = '', children, ...rest }: ComponentPropsWithRef<'select'>) {
  return (
    <select
      {...rest}
      className={`w-full rounded-lg border border-hairline bg-surface px-3 py-2 text-sm text-ink focus:border-series-1 focus:outline-none ${className}`}
    >
      {children}
    </select>
  )
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

/** A status, always as colour + glyph + word. There is no way to render one
 *  of the three without the others, which is the point. */
export function StatusChip({
  status,
  count,
  size = 'md',
  className = '',
}: {
  status: string
  count?: number
  size?: 'sm' | 'md'
  className?: string
}) {
  const style = statusStyle(status)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-medium ${
        size === 'sm' ? 'text-[11px]' : 'text-xs'
      } ${className}`}
      style={{ borderColor: style.color, background: style.wash, color: style.color }}
      title={style.description}
    >
      <span aria-hidden="true" className="font-bold">
        {style.glyph}
      </span>
      {style.label}
      {count !== undefined && <span className="tabular-nums opacity-80">{count}</span>}
    </span>
  )
}

export function Badge({
  children,
  color,
  glyph,
  wash,
}: {
  children: ReactNode
  color?: string
  glyph?: string
  wash?: string
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 text-xs text-ink-2"
      style={color ? { borderColor: color, color, background: wash } : undefined}
    >
      {glyph && (
        <span aria-hidden="true" className="font-bold">
          {glyph}
        </span>
      )}
      {children}
    </span>
  )
}

/** A single headline number, with the sentence that says what it means.
 *  `detail` is not optional decoration here -- the house rule is that no
 *  figure appears without one. */
export function StatTile({
  label,
  value,
  detail,
  tone,
  hint,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: string
  hint?: string
}) {
  return (
    <div className="rounded-lg border border-hairline bg-surface-2 px-3.5 py-3">
      <div className="flex items-center gap-1.5 text-xs text-muted">
        {label}
        {hint && <InfoHint text={hint} />}
      </div>
      <div
        className="mt-1 text-xl font-semibold tabular-nums"
        style={tone ? { color: tone } : undefined}
      >
        {value}
      </div>
      {detail && <div className="mt-0.5 text-xs leading-snug text-muted">{detail}</div>}
    </div>
  )
}

/** A "?" that explains a term in place. The app is full of words a first-time
 *  reader has no reason to know; this is cheaper than a glossary they have to
 *  go and find. */
export function InfoHint({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="What does this mean?"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-hairline text-[9px] font-bold text-muted transition hover:border-series-1 hover:text-series-1"
      >
        ?
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-1/2 top-5 z-30 w-60 -translate-x-1/2 rounded-lg border border-hairline bg-surface p-2.5 text-xs font-normal leading-snug text-ink-2 shadow-[var(--shadow-float)]"
        >
          {text}
        </span>
      )}
    </span>
  )
}

export function Banner({
  tone = 'info',
  title,
  children,
  onDismiss,
  actions,
}: {
  tone?: 'info' | 'warning' | 'critical' | 'good'
  title?: string
  children: ReactNode
  onDismiss?: () => void
  actions?: ReactNode
}) {
  const colors: Record<string, string> = {
    info: 'var(--series-1)',
    good: 'var(--good)',
    warning: 'var(--warning)',
    critical: 'var(--critical)',
  }
  const washes: Record<string, string> = {
    info: 'transparent',
    good: 'var(--good-wash)',
    warning: 'var(--warning-wash)',
    critical: 'var(--critical-wash)',
  }
  const glyphs: Record<string, string> = { info: 'i', good: '✓', warning: '!', critical: '✗' }

  return (
    <div
      className="flex gap-3 rounded-lg border px-4 py-3 text-sm text-ink-2"
      style={{ borderColor: colors[tone], background: washes[tone] }}
      role={tone === 'critical' ? 'alert' : undefined}
    >
      <span
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-sm font-bold"
        style={{ color: colors[tone] }}
      >
        {glyphs[tone]}
      </span>
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold text-ink">{title}</div>}
        <div className="break-words">{children}</div>
        {actions && <div className="mt-2 flex flex-wrap gap-2">{actions}</div>}
      </div>
      {onDismiss && (
        <IconButton label="Dismiss" onClick={onDismiss}>
          ✕
        </IconButton>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string
  children?: ReactNode
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="rounded-lg border border-dashed border-hairline px-4 py-8 text-center">
      {icon && <div className="mb-2 text-2xl opacity-40">{icon}</div>}
      <p className="text-sm font-medium text-ink-2">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-[52ch] text-xs text-muted">{children}</p>}
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  )
}

export function Section({
  title,
  count,
  hint,
  children,
  defaultOpen = true,
  collapsible = false,
}: {
  title: string
  count?: number
  hint?: string
  children: ReactNode
  defaultOpen?: boolean
  collapsible?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const header = (
    <span className="flex items-center gap-2">
      {collapsible && (
        <span
          aria-hidden="true"
          className={`inline-block text-muted transition-transform ${open ? 'rotate-90' : ''}`}
        >
          ▸
        </span>
      )}
      <span className="text-sm font-semibold text-ink">{title}</span>
      {count !== undefined && (
        <span className="rounded-full bg-surface-2 px-1.5 text-xs tabular-nums text-muted">
          {count}
        </span>
      )}
      {hint && <InfoHint text={hint} />}
    </span>
  )
  return (
    <div>
      {collapsible ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="mb-2 w-full text-left"
        >
          {header}
        </button>
      ) : (
        <div className="mb-2">{header}</div>
      )}
      {open && children}
    </div>
  )
}

/** Tabs that say what each one is for. A bare word is not enough when the
 *  words are "Setup", "Results" and "History". */
export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  className = '',
}: {
  tabs: Array<{ id: T; label: string; hint?: string; badge?: ReactNode }>
  active: T
  onChange: (id: T) => void
  className?: string
}) {
  return (
    <div className={`flex gap-1 border-b border-hairline ${className}`} role="tablist">
      {tabs.map((tab) => {
        const selected = tab.id === active
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            title={tab.hint}
            className={`-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition ${
              selected
                ? 'border-series-1 text-ink'
                : 'border-transparent text-muted hover:border-hairline hover:text-ink-2'
            }`}
          >
            {tab.label}
            {tab.badge}
          </button>
        )
      })}
    </div>
  )
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className = '',
}: {
  options: Array<{ value: T; label: string; disabled?: boolean }>
  value: T
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div className={`inline-flex gap-0.5 rounded-lg border border-hairline bg-surface-2 p-0.5 ${className}`}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          className={`rounded-md px-3 py-1 text-xs font-medium transition disabled:opacity-40 ${
            value === option.value
              ? 'bg-surface text-ink shadow-[var(--shadow-card)]'
              : 'text-muted hover:text-ink-2'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/** A score as a bar *and* a written percentage *and* a word. */
export function ScoreBar({
  value,
  label = 'match',
  size = 'md',
}: {
  value: number | null
  label?: string
  size?: 'sm' | 'md'
}) {
  if (value === null) {
    return <span className="text-xs text-muted">not measured</span>
  }
  const tone =
    value >= 90 ? 'var(--good)' : value >= 70 ? 'var(--warning)' : 'var(--critical)'
  return (
    <div className="flex items-center gap-2">
      <div
        className={`relative overflow-hidden rounded-full bg-surface-3 ${
          size === 'sm' ? 'h-1.5 w-16' : 'h-2 w-24'
        }`}
        role="img"
        aria-label={`${value}% ${label}`}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: tone }}
        />
      </div>
      <span className="whitespace-nowrap text-xs font-medium tabular-nums" style={{ color: tone }}>
        {value}% {label}
      </span>
    </div>
  )
}

/** Replaces `window.confirm` and `window.prompt`.
 *
 * Escape closes it, focus moves into it on open and the confirm button is
 * focused, and the whole thing is a real element an automated check can find --
 * none of which is true of the native dialogs this replaces.
 */
export function Dialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  busy = false,
  input,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  busy?: boolean
  /** When present the dialog is a prompt; the current value is passed back. */
  input?: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }
  onConfirm: () => void
  onCancel: () => void
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const target = input ? inputRef.current : confirmRef.current
    target?.focus()
    if (input) inputRef.current?.select()

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCancel()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, input, onCancel])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onCancel()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-md rounded-xl border border-hairline bg-surface p-5 shadow-[var(--shadow-float)]"
      >
        <h2 className="text-md font-semibold text-ink">{title}</h2>
        {description && (
          <div className="mt-1.5 text-sm leading-relaxed text-ink-2">{description}</div>
        )}

        {input && (
          <div className="mt-4">
            <Field label={input.label}>
              <Input
                ref={inputRef}
                value={input.value}
                placeholder={input.placeholder}
                onChange={(event) => input.onChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    onConfirm()
                  }
                }}
              />
            </Field>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            variant={danger ? 'danger' : 'primary'}
            loading={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function ThemeToggle({
  choice,
  onChange,
}: {
  choice: ThemeChoice
  onChange: (choice: ThemeChoice) => void
}) {
  const options: Array<{ value: ThemeChoice; label: string; glyph: string }> = [
    { value: 'light', label: 'Light', glyph: '☀' },
    { value: 'dark', label: 'Dark', glyph: '☾' },
    { value: 'system', label: 'System', glyph: '◐' },
  ]
  return (
    <div
      className="inline-flex gap-0.5 rounded-lg border border-hairline bg-surface-2 p-0.5"
      role="group"
      aria-label="Colour theme"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={choice === option.value}
          title={`${option.label} theme`}
          className={`flex-1 rounded-md px-2 py-1 text-xs transition ${
            choice === option.value
              ? 'bg-surface text-ink shadow-[var(--shadow-card)]'
              : 'text-muted hover:text-ink-2'
          }`}
        >
          <span aria-hidden="true">{option.glyph}</span>
          <span className="sr-only">{option.label}</span>
        </button>
      ))}
    </div>
  )
}

/** Horizontal rule with a word on it, for splitting a long panel. */
export function Divider({ children }: { children?: ReactNode }) {
  if (!children) return <hr className="my-4 border-0 border-t border-hairline" />
  return (
    <div className="my-4 flex items-center gap-3">
      <hr className="flex-1 border-0 border-t border-hairline" />
      <span className="text-xs text-muted">{children}</span>
      <hr className="flex-1 border-0 border-t border-hairline" />
    </div>
  )
}

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-xl border border-hairline bg-surface p-6 ${className}`}>
      {(title || actions) && (
        <header className="mb-5 flex items-start justify-between gap-4 border-b border-hairline/60 pb-4">
          <div className="min-w-0">
            {title && <h2 className="text-lg font-semibold text-ink">{title}</h2>}
            {/* Capped at a comfortable measure: a subtitle running the full
                width of a wide card is a paragraph nobody reads. */}
            {subtitle && (
              <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  loading?: boolean
}

export function Button({
  variant = 'secondary',
  loading = false,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  const styles: Record<string, string> = {
    primary: 'bg-series-1 text-white hover:brightness-110',
    secondary: 'bg-surface-2 text-ink border border-hairline hover:border-ink-2/40',
    ghost: 'text-ink-2 hover:text-ink',
    danger: 'text-critical border border-critical/40 hover:bg-critical/10',
  }
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:opacity-45 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    >
      {loading && <Spinner />}
      {children}
    </button>
  )
}

export function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-r-transparent animate-spin"
    />
  )
}

export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`w-full bg-plane border border-hairline rounded-lg px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-series-1 focus:outline-none ${className}`}
    />
  )
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium uppercase tracking-wide text-muted mb-1.5">
        {label}
      </span>
      {children}
      {hint && <span className="block text-xs text-muted mt-1">{hint}</span>}
    </label>
  )
}

export function Badge({
  children,
  color,
  glyph,
}: {
  children: ReactNode
  color?: string
  glyph?: string
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 text-xs text-ink-2"
      style={color ? { borderColor: `${color}66` } : undefined}
    >
      {color && (
        <span
          aria-hidden="true"
          className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-[9px] font-bold text-plane"
          style={{ background: color }}
        >
          {glyph}
        </span>
      )}
      {children}
    </span>
  )
}

/** A single headline number. Used instead of a chart where there is one value
 *  and no comparison to draw. */
export function StatTile({
  label,
  value,
  detail,
  tone,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: string
}) {
  return (
    <div className="bg-surface-2 border border-hairline rounded-lg px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold" style={tone ? { color: tone } : undefined}>
        {value}
      </div>
      {detail && <div className="mt-0.5 text-xs text-muted">{detail}</div>}
    </div>
  )
}

export function Banner({
  tone = 'info',
  title,
  children,
  onDismiss,
}: {
  tone?: 'info' | 'warning' | 'critical' | 'good'
  title?: string
  children: ReactNode
  onDismiss?: () => void
}) {
  const tones: Record<string, string> = {
    info: 'border-series-1/40 text-ink-2',
    good: 'border-good/40 text-ink-2',
    warning: 'border-warning/40 text-ink-2',
    critical: 'border-critical/50 text-ink-2',
  }
  const glyphs: Record<string, string> = {
    info: 'i',
    good: '✓',
    warning: '!',
    critical: '✗',
  }
  // Reference the same design tokens everything else in the app draws from
  // (index.css / lib/theme.ts) rather than re-declaring hex values here --
  // these had drifted from the canonical --color-good and --color-critical,
  // so a "good" banner and a "Conforming" status badge were two different
  // greens.
  const colors: Record<string, string> = {
    info: 'var(--color-series-1)',
    good: 'var(--color-good)',
    warning: 'var(--color-warning)',
    critical: 'var(--color-critical)',
  }
  return (
    <div className={`flex gap-3 rounded-lg border bg-surface px-4 py-3 text-sm ${tones[tone]}`}>
      <span
        aria-hidden="true"
        className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-plane"
        style={{ background: colors[tone] }}
      >
        {glyphs[tone]}
      </span>
      <div className="min-w-0 flex-1">
        {title && <div className="font-medium text-ink">{title}</div>}
        <div className="break-words">{children}</div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className="text-muted hover:text-ink shrink-0"
        >
          ✕
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-hairline px-4 py-8 text-center">
      <p className="text-sm text-ink-2">{title}</p>
      {children && <p className="mt-1 text-xs text-muted">{children}</p>}
    </div>
  )
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink mb-2">{title}</h3>
      {children}
    </div>
  )
}

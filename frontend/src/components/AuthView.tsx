import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, errorMessage } from '../lib/api'
import { Banner, Button, Card, Field, Input } from './ui'

export function AuthView({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const isRegistering = mode === 'register'

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setNotice('')
    setBusy(true)
    try {
      if (isRegistering) {
        await api.register(username, email, password)
        setMode('signin')
        setPassword('')
        setNotice('Account created. Sign in to continue.')
      } else {
        onAuthenticated(await api.login(username, password))
      }
    } catch (caught) {
      setError(errorMessage(caught, 'Authentication failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-semibold text-ink">Polyglot Conformance Platform</h1>
          <p className="mt-1 text-sm text-muted">
            Compare a StarUML design against the code that implements it.
          </p>
        </div>

        <Card>
          <div className="mb-4 flex rounded-lg border border-hairline p-1">
            {(['signin', 'register'] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setMode(value)
                  setError('')
                }}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm transition ${
                  mode === value ? 'bg-surface-2 text-ink' : 'text-muted hover:text-ink-2'
                }`}
              >
                {value === 'signin' ? 'Sign in' : 'Register'}
              </button>
            ))}
          </div>

          {error && (
            <div className="mb-4">
              <Banner tone="critical">{error}</Banner>
            </div>
          )}
          {notice && (
            <div className="mb-4">
              <Banner tone="good">{notice}</Banner>
            </div>
          )}

          <form onSubmit={submit} className="space-y-3">
            <Field label="Username">
              <Input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
                minLength={3}
                maxLength={20}
                autoComplete="username"
              />
            </Field>

            {isRegistering && (
              <Field label="Email">
                <Input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  autoComplete="email"
                />
              </Field>
            )}

            <Field
              label="Password"
              hint={isRegistering ? 'At least 8 characters.' : undefined}
            >
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={isRegistering ? 8 : undefined}
                autoComplete={isRegistering ? 'new-password' : 'current-password'}
              />
            </Field>

            <Button type="submit" variant="primary" loading={busy} className="w-full">
              {isRegistering ? 'Create account' : 'Sign in'}
            </Button>
          </form>
        </Card>
      </div>
    </main>
  )
}

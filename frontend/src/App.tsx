import { useCallback, useEffect, useState } from 'react'
import { AuthView } from './components/AuthView'
import { Dashboard } from './components/Dashboard'
import { ProjectWorkspace } from './components/ProjectWorkspace'
import { StatisticsPage } from './components/StatisticsPage'
import { ToastProvider, useToast } from './components/Toast'
import { Banner } from './components/ui'
import { TOKEN_KEY, api, errorMessage, isNetworkError, setUnauthorizedHandler } from './lib/api'
import type { ProjectSummary, PublicConfig, Repo } from './lib/types'

function Shell() {
  const toast = useToast()
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [githubConnected, setGithubConnected] = useState(false)
  const [repos, setRepos] = useState<Repo[]>([])
  const [activeProject, setActiveProject] = useState<string | null>(null)
  const [showStatistics, setShowStatistics] = useState(false)
  const [connectionError, setConnectionError] = useState('')
  // Distinguishes "the server never answered" from "the server answered with
  // an error" -- the two look identical if all you check is whether a
  // request failed, but they are not the same problem for the user to chase.
  const [connectionUnreachable, setConnectionUnreachable] = useState(false)

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setActiveProject(null)
    setShowStatistics(false)
    setProjects([])
    setRepos([])
    setGithubConnected(false)
  }, [])

  // A 401 anywhere returns the user to the sign-in screen instead of leaving a
  // permanent "cannot reach the server" banner with no way forward.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null)
      setActiveProject(null)
    })
  }, [])

  useEffect(() => {
    api
      .config()
      .then(setConfig)
      .catch((caught) => {
        setConnectionError(errorMessage(caught, 'Could not reach the backend server.'))
        setConnectionUnreachable(isNetworkError(caught))
      })
  }, [])

  const refresh = useCallback(async () => {
    if (!localStorage.getItem(TOKEN_KEY)) return
    try {
      const [projectList, status] = await Promise.all([api.projects(), api.githubStatus()])
      setProjects(projectList)
      setGithubConnected(status.is_connected)
      setConnectionError('')

      if (status.is_connected) {
        try {
          setRepos(await api.githubRepos())
        } catch {
          // A stale GitHub token should not break the whole dashboard.
          setRepos([])
        }
      } else {
        setRepos([])
      }
    } catch (caught) {
      setConnectionError(errorMessage(caught, 'Could not reach the backend server.'))
      setConnectionUnreachable(isNetworkError(caught))
    }
  }, [])

  useEffect(() => {
    if (token) void refresh()
  }, [token, refresh])

  // GitHub redirects back with ?code=…; exchange it once, then clean the URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const oauthError = params.get('error_description') ?? params.get('error')

    if (oauthError) {
      window.history.replaceState({}, document.title, window.location.pathname)
      toast.notify(`GitHub authorisation failed: ${oauthError}`, 'critical')
      return
    }
    if (!code) return

    if (!localStorage.getItem(TOKEN_KEY)) {
      // Previously the code was silently dropped in this case and the user was
      // left wondering why nothing happened.
      toast.notify('Sign in first, then connect GitHub — the authorisation code was discarded.', 'warning')
      window.history.replaceState({}, document.title, window.location.pathname)
      return
    }

    window.history.replaceState({}, document.title, window.location.pathname)
    api
      .githubCallback(code)
      .then(async () => {
        toast.notify('GitHub connected.', 'good')
        await refresh()
      })
      .catch((caught) => toast.notify(errorMessage(caught), 'critical'))
  }, [token, refresh, toast])

  if (!token) {
    return (
      <>
        {connectionError && (
          <div className="mx-auto max-w-sm p-6 pb-0">
            <Banner tone="critical" title={connectionUnreachable ? 'Backend unreachable' : 'Connection problem'}>
              {connectionError}
            </Banner>
          </div>
        )}
        <AuthView
          onAuthenticated={(newToken) => {
            localStorage.setItem(TOKEN_KEY, newToken)
            setToken(newToken)
          }}
        />
      </>
    )
  }

  return (
    <>
      {connectionError && (
        <div className="mx-auto max-w-5xl p-6 pb-0">
          <Banner
            tone="critical"
            title={connectionUnreachable ? 'Backend unreachable' : 'Connection problem'}
            onDismiss={() => setConnectionError('')}
          >
            {connectionError}
          </Banner>
        </div>
      )}
      {showStatistics ? (
        <StatisticsPage onBack={() => setShowStatistics(false)} />
      ) : activeProject ? (
        <ProjectWorkspace
          projectName={activeProject}
          config={config}
          onBack={() => {
            setActiveProject(null)
            void refresh()
          }}
        />
      ) : (
        <Dashboard
          config={config}
          projects={projects}
          githubConnected={githubConnected}
          repos={repos}
          onRefresh={refresh}
          onOpen={setActiveProject}
          onSignOut={signOut}
          onOpenStatistics={() => setShowStatistics(true)}
        />
      )}
    </>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  )
}

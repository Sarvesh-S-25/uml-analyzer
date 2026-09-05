import axios from 'axios'
import type { StatisticsReport } from './statsTypes'
import type {
  AnalysisResult,
  Benchmark,
  FileContent,
  GateStrategy,
  GraphData,
  Metrics,
  ModelComparison,
  ProjectSummary,
  PublicConfig,
  Repo,
  RunRow,
  Spread,
  TreeNode,
  UmlModelInfo,
  VersionRecord,
  WorkspaceStats,
} from './types'

// Configurable per environment instead of hardcoded to localhost, so a build
// can point at a deployed backend without editing source.
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000'

export const TOKEN_KEY = 'conformance.token'

const client = axios.create({ baseURL: API_BASE })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    // A 401 means the session is gone. Previously this surfaced as a permanent
    // "could not reach the server" banner with no way out.
    if (error?.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      onUnauthorized?.()
    }
    return Promise.reject(error)
  },
)

/** True only when the request never reached a server at all (DNS, refused
 *  connection, CORS block) -- as opposed to the server responding with an
 *  error status, which means it is very much reachable. Callers use this to
 *  choose an honest banner title instead of labelling every failure
 *  "backend unreachable". */
export function isNetworkError(error: unknown): boolean {
  return axios.isAxiosError(error) && error.code === 'ERR_NETWORK'
}

/** Extract a human-readable message from an axios error. */
export function errorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0]
      if (typeof first?.msg === 'string') {
        const field = Array.isArray(first.loc) ? first.loc.slice(-1)[0] : ''
        return field ? `${field}: ${first.msg}` : first.msg
      }
    }
    if (error.code === 'ERR_NETWORK') {
      return `Cannot reach the backend at ${API_BASE}. Is it running?`
    }
    return error.message || fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}

const project = (name: string) => `/projects/${encodeURIComponent(name)}`

export const api = {
  config: () => client.get<PublicConfig>('/config').then((r) => r.data),

  register: (username: string, email: string, password: string) =>
    client.post('/register', { username, email, password }).then((r) => r.data),

  login: async (username: string, password: string) => {
    const params = new URLSearchParams()
    params.append('username', username)
    params.append('password', password)
    const response = await client.post<{ access_token: string }>('/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return response.data.access_token
  },

  // --- GitHub (entirely optional) -------------------------------------------

  githubStatus: () => client.get<{ is_connected: boolean }>('/github/status').then((r) => r.data),
  githubRepos: () => client.get<{ repos: Repo[] }>('/github/repos').then((r) => r.data.repos),
  githubCallback: (code: string) => client.post('/github/callback', { code }).then((r) => r.data),
  githubDisconnect: () => client.post('/github/disconnect').then((r) => r.data),

  // --- projects --------------------------------------------------------------

  projects: () =>
    client.get<{ projects: ProjectSummary[] }>('/projects').then((r) => r.data.projects),

  createProject: (name: string, githubRepoFullName: string | null) =>
    client
      .post<{ project_name: string }>('/projects', {
        name,
        github_repo_full_name: githubRepoFullName,
      })
      .then((r) => r.data),

  deleteProject: (name: string) => client.delete(`${project(name)}`),

  // --- the virtual directory --------------------------------------------------

  tree: (name: string) =>
    client
      .get<{ tree: TreeNode[]; stats: WorkspaceStats }>(`${project(name)}/tree`)
      .then((r) => r.data),

  readFile: (name: string, path: string) =>
    client
      .get<FileContent>(`${project(name)}/files`, { params: { path } })
      .then((r) => r.data),

  createFile: (name: string, path: string, content = '') =>
    client.post(`${project(name)}/files`, { path, content }).then((r) => r.data),

  saveFile: (name: string, path: string, content: string) =>
    client.put(`${project(name)}/files`, { path, content }).then((r) => r.data),

  deleteFile: (name: string, path: string) =>
    client.delete(`${project(name)}/files`, { params: { path } }).then((r) => r.data),

  moveFile: (name: string, source: string, destination: string) =>
    client.post(`${project(name)}/files/move`, { source, destination }).then((r) => r.data),

  createFolder: (name: string, path: string) =>
    client.post(`${project(name)}/folders`, { path }).then((r) => r.data),

  clearSource: (name: string) => client.delete(`${project(name)}/source`).then((r) => r.data),

  uploadSource: (name: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post(`${project(name)}/upload/source`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  /** Upload many files at once, preserving each one's path within the folder. */
  uploadBatch: (name: string, files: File[], paths: string[]) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    form.append('paths', JSON.stringify(paths))
    return client
      .post<{ written: string[]; rejected: Array<{ path: string; reason: string }> }>(
        `${project(name)}/upload/source-batch`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      .then((r) => r.data)
  },

  exportUrl: (name: string) => `${API_BASE}${project(name)}/export`,

  downloadExport: (name: string) =>
    client.get(`${project(name)}/export`, { responseType: 'blob' }).then((r) => r.data as Blob),

  // --- UML ---------------------------------------------------------------------

  umlModels: (name: string) =>
    client.get<{ models: UmlModelInfo[] }>(`${project(name)}/uml`).then((r) => r.data.models),

  uploadUml: (name: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<{ models: UmlModelInfo[] }>(`${project(name)}/upload/uml`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  deleteUml: (name: string, filename: string) =>
    client
      .delete<{ models: UmlModelInfo[] }>(
        `${project(name)}/uml/${encodeURIComponent(filename)}`,
      )
      .then((r) => r.data),

  // --- analysis -----------------------------------------------------------------

  analyze: (name: string, gateStrategy: GateStrategy, force = false) =>
    client
      .post<AnalysisResult>(`${project(name)}/analyze`, {
        gate_strategy: gateStrategy,
        force,
      })
      .then((r) => r.data),

  versions: (name: string) =>
    client
      .get<{ versions: VersionRecord[]; max_versions: number }>(`${project(name)}/versions`)
      .then((r) => r.data),

  versionGraph: (name: string, version: number) =>
    client
      .get<{ graph_data: GraphData }>(`${project(name)}/versions/${version}/graph`)
      .then((r) => r.data.graph_data),

  metrics: (name: string) =>
    client
      .get<{ metrics: Metrics; runs: RunRow[] }>(`${project(name)}/metrics`)
      .then((r) => r.data),

  benchmark: (name: string) =>
    client.get<Benchmark>(`${project(name)}/benchmark`).then((r) => r.data),

  explain: (name: string, filePath: string) =>
    client
      .post<{ explanation: string; model: string; invoked: boolean }>(
        `${project(name)}/explain`,
        { file_path: filePath },
      )
      .then((r) => r.data),

  // --- research ------------------------------------------------------------------

  repeatability: (name: string, runs: number) =>
    client
      .post<{
        runs: number
        llm_enabled: boolean
        similarity_score: Spread
        gap_count: Spread
        graph_node_count: Spread
        note: string
      }>(`${project(name)}/repeatability`, { runs })
      .then((r) => r.data),

  modelComparison: (name: string, models: string[]) =>
    client
      .post<ModelComparison>(`${project(name)}/model-comparison`, { models })
      .then((r) => r.data),

  // --- statistics ------------------------------------------------------------

  statistics: (projects: string[] = []) =>
    client.post<StatisticsReport>('/statistics', { projects }).then((r) => r.data),

  projectStatistics: (name: string) =>
    client.get<StatisticsReport>(`${project(name)}/statistics`).then((r) => r.data),

  /** Server-side export: a zip of CSVs, one combined CSV, or LaTeX tables. */
  downloadStatistics: (projects: string[], format: 'zip' | 'csv' | 'latex') =>
    client
      .post('/statistics/export', { projects }, {
        params: { fmt: format },
        responseType: 'blob',
      })
      .then((r) => r.data as Blob),
}

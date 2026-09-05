/** Turn the backend's flat path list into a real folder hierarchy.
 *
 * `GET /projects/{name}/tree` returns one entry per path with no nesting, and
 * the old file panel rendered that list verbatim — indenting each row by the
 * number of slashes in its path and calling it a tree. Nothing could be
 * collapsed, a folder was just a row that did nothing when clicked, and a
 * project of any size was an unbroken scroll.
 *
 * This rebuilds the structure the paths imply. Intermediate folders are
 * synthesised when the backend did not send them, so a response containing only
 * blobs still produces a browsable tree rather than a flat pile.
 */
import type { TreeNode } from './types'

export interface TreeEntry {
  /** Just this segment, e.g. `OrderService.java`. */
  name: string
  /** The full path from the project root, which is what the API wants. */
  path: string
  type: 'tree' | 'blob'
  size: number | null
  editable: boolean
  children: TreeEntry[]
  /** Files at or below this folder. Zero for a blob. */
  fileCount: number
  /** Total bytes at or below this folder. */
  totalSize: number
  depth: number
}

function emptyFolder(name: string, path: string, depth: number): TreeEntry {
  return {
    name,
    path,
    type: 'tree',
    size: null,
    editable: false,
    children: [],
    fileCount: 0,
    totalSize: 0,
    depth,
  }
}

export function buildTree(nodes: TreeNode[]): TreeEntry[] {
  const root = emptyFolder('', '', -1)
  const folders = new Map<string, TreeEntry>([['', root]])

  /** Walk down from the root, creating folders that do not exist yet. */
  function folderAt(path: string): TreeEntry {
    const existing = folders.get(path)
    if (existing) return existing

    const segments = path.split('/')
    const name = segments[segments.length - 1]
    const parentPath = segments.slice(0, -1).join('/')
    const parent = folderAt(parentPath)

    const created = emptyFolder(name, path, parent.depth + 1)
    parent.children.push(created)
    folders.set(path, created)
    return created
  }

  // Folders first, so an explicitly-sent folder keeps its own metadata rather
  // than being synthesised later from a child's path.
  for (const node of nodes) {
    if (node.type !== 'tree') continue
    folderAt(node.path)
  }

  for (const node of nodes) {
    if (node.type !== 'blob') continue
    const segments = node.path.split('/')
    const name = segments[segments.length - 1]
    const parent = folderAt(segments.slice(0, -1).join('/'))
    parent.children.push({
      name,
      path: node.path,
      type: 'blob',
      size: node.size,
      editable: node.editable,
      children: [],
      fileCount: 0,
      totalSize: node.size ?? 0,
      depth: parent.depth + 1,
    })
  }

  // Roll counts up from the leaves, then sort: folders before files, each
  // alphabetically and case-insensitively, so the order never depends on the
  // order the backend happened to send.
  function finalise(entry: TreeEntry): void {
    if (entry.type === 'blob') return
    entry.children.forEach(finalise)
    entry.children.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'tree' ? -1 : 1
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    })
    entry.fileCount = entry.children.reduce(
      (total, child) => total + (child.type === 'blob' ? 1 : child.fileCount),
      0,
    )
    entry.totalSize = entry.children.reduce((total, child) => total + child.totalSize, 0)
  }
  finalise(root)

  return root.children
}

/** Every folder path in the tree — what "expand all" needs. */
export function allFolderPaths(entries: TreeEntry[]): string[] {
  const found: string[] = []
  const walk = (list: TreeEntry[]) => {
    for (const entry of list) {
      if (entry.type !== 'tree') continue
      found.push(entry.path)
      walk(entry.children)
    }
  }
  walk(entries)
  return found
}

/** Each ancestor folder of a path, root-first. Used to reveal a file. */
export function ancestorsOf(path: string): string[] {
  const segments = path.split('/').slice(0, -1)
  return segments.map((_, index) => segments.slice(0, index + 1).join('/'))
}

/** Folders that should open by default.
 *
 * A repository whose real code sits under `src/main/java/com/example/app` would
 * otherwise open on a single closed folder, and every visitor's first action
 * would be five clicks to get anywhere. So descend through folders that hold
 * nothing but one more folder, and open those.
 */
export function defaultOpenFolders(entries: TreeEntry[], limit = 40): string[] {
  const open: string[] = []
  let level = entries
  while (open.length < limit) {
    const folders = level.filter((entry) => entry.type === 'tree')
    const files = level.filter((entry) => entry.type === 'blob')
    if (folders.length !== 1 || files.length > 0) break
    open.push(folders[0].path)
    level = folders[0].children
  }
  // Also open the top level's folders when the project is small enough that
  // showing everything is not overwhelming.
  const total = entries.reduce(
    (sum, entry) => sum + (entry.type === 'blob' ? 1 : entry.fileCount),
    0,
  )
  if (total <= 25) {
    for (const path of allFolderPaths(entries)) {
      if (!open.includes(path) && open.length < limit) open.push(path)
    }
  }
  return open
}

/** Keep only entries matching `needle`, plus the folders leading to them.
 *
 * Returns the pruned tree and the folders that must be open for the matches to
 * be visible — a filtered tree whose results are hidden inside closed folders
 * is worse than no filter at all.
 */
export function filterTree(
  entries: TreeEntry[],
  needle: string,
): { entries: TreeEntry[]; expand: string[] } {
  const query = needle.trim().toLowerCase()
  if (!query) return { entries, expand: [] }

  const expand: string[] = []

  function prune(list: TreeEntry[]): TreeEntry[] {
    const kept: TreeEntry[] = []
    for (const entry of list) {
      if (entry.type === 'blob') {
        if (entry.path.toLowerCase().includes(query)) kept.push(entry)
        continue
      }
      const children = prune(entry.children)
      const selfMatches = entry.name.toLowerCase().includes(query)
      if (children.length > 0 || selfMatches) {
        // A folder whose own name matched keeps all of its contents; one that
        // only contains matches keeps just those.
        const next = selfMatches && children.length === 0 ? entry.children : children
        kept.push({ ...entry, children: next })
        expand.push(entry.path)
      }
    }
    return kept
  }

  return { entries: prune(entries), expand }
}

/** How many files matched, for the "12 of 480 files" line under the filter. */
export function countFiles(entries: TreeEntry[]): number {
  return entries.reduce(
    (total, entry) => total + (entry.type === 'blob' ? 1 : countFiles(entry.children)),
    0,
  )
}

/** Language for an extension — drives the icon letter and the highlighter. */
export function languageOf(path: string): string {
  const extension = path.slice(path.lastIndexOf('.') + 1).toLowerCase()
  switch (extension) {
    case 'java':
      return 'java'
    case 'py':
      return 'python'
    case 'ts':
    case 'tsx':
      return 'typescript'
    case 'js':
    case 'jsx':
    case 'mjs':
    case 'cjs':
      return 'javascript'
    case 'cs':
      return 'csharp'
    case 'go':
      return 'go'
    case 'rb':
      return 'ruby'
    case 'php':
      return 'php'
    case 'kt':
    case 'kts':
      return 'kotlin'
    case 'json':
      return 'json'
    case 'md':
      return 'markdown'
    case 'xml':
    case 'html':
      return 'markup'
    case 'css':
      return 'css'
    case 'yml':
    case 'yaml':
      return 'yaml'
    case 'mdj':
      return 'diagram'
    default:
      return 'text'
  }
}

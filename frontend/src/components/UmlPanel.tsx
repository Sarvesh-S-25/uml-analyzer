import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { api, errorMessage } from '../lib/api'
import type { UmlModelInfo } from '../lib/types'
import { formatDate } from '../lib/theme'
import { useToast } from './Toast'
import { Badge, Banner, Button, Card, EmptyState } from './ui'

/** StarUML model management.
 *
 * The pipeline analyses one model at a time, and it picks the alphabetically
 * first. That is stated here rather than left implicit, because a project with
 * two diagrams and no visible indication of which one is in force produces
 * results nobody can interpret.
 */
export function UmlPanel({
  projectName,
  onChanged,
}: {
  projectName: string
  onChanged: () => void
}) {
  const toast = useToast()
  const [models, setModels] = useState<UmlModelInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)

  async function refresh() {
    try {
      setModels(await api.umlModels(projectName))
      setError('')
    } catch (caught) {
      setError(errorMessage(caught, 'Could not list the UML models.'))
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectName])

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const response = await api.uploadUml(projectName, file)
      setModels(response.models)
      onChanged()
      toast.notify(`Uploaded ${file.name}.`, 'good')
    } catch (caught) {
      // A malformed .mdj is rejected here rather than silently producing a
      // score against an empty design later.
      toast.notify(errorMessage(caught, 'Upload failed.'), 'critical')
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  async function remove(filename: string) {
    if (!window.confirm(`Remove the model “${filename}”?`)) return
    try {
      const response = await api.deleteUml(projectName, filename)
      setModels(response.models)
      onChanged()
      toast.notify(`Removed ${filename}.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

  return (
    <Card
      title="Design model"
      subtitle="The StarUML (.mdj) diagram the code is checked against."
      actions={
        <Button onClick={() => input.current?.click()} loading={uploading}>
          Upload .mdj
        </Button>
      }
    >
      <input
        ref={input}
        type="file"
        accept=".mdj"
        className="hidden"
        onChange={upload}
      />

      {error && (
        <div className="mb-3">
          <Banner tone="critical">{error}</Banner>
        </div>
      )}

      {models.length === 0 ? (
        <EmptyState title="No diagram uploaded">
          Export your StarUML project as .mdj and upload it. Without one, the analysis reports
          the code's structure but has nothing to compare it against.
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {models.map((model) => (
            <li
              key={model.filename}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm text-ink">{model.filename}</span>
                  {model.active && (
                    <Badge color="#199e70" glyph="✓">
                      In use
                    </Badge>
                  )}
                </div>
                <div className="text-xs text-muted">
                  {Math.round(model.size / 1024)} KB · {formatDate(model.modified_at)}
                </div>
              </div>
              <Button variant="ghost" onClick={() => remove(model.filename)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      {models.length > 1 && (
        <p className="mt-3 text-xs text-muted">
          Several models are present. Analysis uses the first alphabetically —
          <span className="text-ink-2"> {models[0].filename}</span>. Remove the others to be
          unambiguous.
        </p>
      )}
    </Card>
  )
}

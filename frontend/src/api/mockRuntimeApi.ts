import samplePayload from './frontend_contract_sample.json'
import type {
  BackendJob,
  MediaSubmissionPayload,
  RuntimeApi,
  RuntimeUiState,
  VisualizerNode,
  VisualizerPayload,
} from './runtimeApi'

function parsePath(path: string): Array<string | number> {
  const out: Array<string | number> = []
  const normalized = path.replace(/\[(\d+)\]/g, '.$1')
  for (const part of normalized.split('.').filter(Boolean)) {
    if (/^\d+$/.test(part)) out.push(Number(part))
    else out.push(part)
  }
  return out
}

function getByPath(root: unknown, path: string): unknown {
  const tokens = parsePath(path)
  let cur: unknown = root
  for (const token of tokens) {
    if (cur == null) return undefined
    if (typeof token === 'number') {
      if (!Array.isArray(cur)) return undefined
      cur = cur[token]
    } else {
      if (typeof cur !== 'object') return undefined
      cur = (cur as Record<string, unknown>)[token]
    }
  }
  return cur
}

function setByPath(root: unknown, path: string, value: unknown): boolean {
  const tokens = parsePath(path)
  if (tokens.length === 0 || root == null || typeof root !== 'object') return false
  let cur: unknown = root
  for (let i = 0; i < tokens.length - 1; i += 1) {
    const token = tokens[i]
    const nextToken = tokens[i + 1]
    if (typeof token === 'number') {
      if (!Array.isArray(cur)) return false
      if (cur[token] == null) {
        cur[token] = typeof nextToken === 'number' ? [] : {}
      }
      cur = cur[token]
    } else {
      if (typeof cur !== 'object' || cur == null) return false
      const dict = cur as Record<string, unknown>
      if (dict[token] == null) {
        dict[token] = typeof nextToken === 'number' ? [] : {}
      }
      cur = dict[token]
    }
  }

  const last = tokens[tokens.length - 1]
  if (typeof last === 'number') {
    if (!Array.isArray(cur)) return false
    cur[last] = value
    return true
  }
  if (typeof cur !== 'object' || cur == null) return false
  ;(cur as Record<string, unknown>)[last] = value
  return true
}

function coerceInputValue(raw: string, existing: unknown): unknown {
  if (raw === '__NULL__') return null
  if (Array.isArray(existing)) {
    const trimmed = raw.trim()
    if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (Array.isArray(parsed)) return parsed
      } catch {
        // fallback below
      }
    }
    return raw
      .split('\n')
      .map((v) => v.trim())
      .filter(Boolean)
  }
  if (typeof existing === 'number') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : existing
  }
  if (typeof existing === 'boolean') {
    return raw.trim().toLowerCase() === 'true'
  }
  if (existing && typeof existing === 'object') {
    try {
      return JSON.parse(raw)
    } catch {
      return existing
    }
  }
  return raw
}

export class MockRuntimeApi implements RuntimeApi {
  private jobs: BackendJob[] = []
  private payload: VisualizerPayload = JSON.parse(JSON.stringify(samplePayload)) as VisualizerPayload

  async getUiState(): Promise<RuntimeUiState> {
    return {
      runtime_mode: 'online',
      deployment_mode: 'local',
      badges: {
        mode: 'Mode: online',
        deployment: 'Deployment: local',
        backend_jobs: 'Backend jobs: on',
        phonetic: 'Phonetic: on',
      },
      features: {
        phonetic: { enabled: true, reason_if_disabled: '' },
        db_persistence: { enabled: true, reason_if_disabled: '' },
        backend_jobs: { enabled: true, reason_if_disabled: '' },
      },
    }
  }

  async submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
  }): Promise<MediaSubmissionPayload> {
    if (input.durationSec <= 900 && input.sizeBytes <= 250 * 1024 * 1024) {
      return {
        result: { route: 'local', message: 'File accepted for local processing.' },
        ui_feedback: {
          severity: 'info',
          title: 'Local processing started',
          message: 'File accepted for local processing.',
        },
      }
    }
    if (input.sizeBytes <= 2048 * 1024 * 1024) {
      const job: BackendJob = {
        id: `job-${this.jobs.length + 1}`,
        status: 'queued',
        media_path: input.mediaPath,
        duration_seconds: input.durationSec,
        size_bytes: input.sizeBytes,
      }
      this.jobs.unshift(job)
      return {
        result: { route: 'backend', message: 'Queued for backend processing.', job_id: job.id },
        ui_feedback: {
          severity: 'warning',
          title: 'Queued for backend processing',
          message: `Queued for backend processing. Job ID: ${job.id}`,
        },
      }
    }
    return {
      result: { route: 'reject', message: 'File exceeds backend size limit.' },
      ui_feedback: {
        severity: 'error',
        title: 'File rejected by media policy',
        message: 'File exceeds backend size limit.',
      },
    }
  }

  async listBackendJobs(): Promise<BackendJob[]> {
    return this.jobs
  }

  async getVisualizerPayload(): Promise<VisualizerPayload> {
    return this.payload
  }

  async applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
  }): Promise<{ status: 'ok' | 'error'; message: string }> {
    const root = this.payload[input.sentenceText]
    if (!root) {
      return { status: 'error', message: 'Sentence not found.' }
    }
    const stack: VisualizerNode[] = [root]
    while (stack.length > 0) {
      const node = stack.pop() as VisualizerNode
      if (node.node_id === input.nodeId) {
        const current = getByPath(node, input.fieldPath)
        const nextValue = coerceInputValue(input.newValue, current)
        if (!setByPath(node, input.fieldPath, nextValue)) {
          return { status: 'error', message: `Invalid field path: ${input.fieldPath}` }
        }
        return { status: 'ok', message: 'Edit applied.' }
      }
      for (const child of node.linguistic_elements) stack.push(child)
    }
    return { status: 'error', message: 'node_id not found.' }
  }
}

import samplePayload from './frontend_contract_sample.json'
import type {
  BackendJob,
  MediaSubmissionPayload,
  RuntimeApi,
  RuntimeUiState,
  VisualizerNode,
  VisualizerPayload,
} from './runtimeApi'

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
    if (input.fieldPath !== 'content') {
      return { status: 'error', message: 'Mock supports only `content` field path.' }
    }
    const stack: VisualizerNode[] = [root]
    while (stack.length > 0) {
      const node = stack.pop() as VisualizerNode
      if (node.node_id === input.nodeId) {
        node.content = input.newValue
        const words = input.newValue.trim().split(/\s+/).filter(Boolean)
        const directLeafChildren = node.linguistic_elements.filter((c) => c.linguistic_elements.length === 0)
        if (directLeafChildren.length === words.length && words.length > 0) {
          directLeafChildren.forEach((child, idx) => {
            child.content = words[idx]
          })
        }
        return { status: 'ok', message: 'Edit applied.' }
      }
      for (const child of node.linguistic_elements) stack.push(child)
    }
    return { status: 'error', message: 'node_id not found.' }
  }
}

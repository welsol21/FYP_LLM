import type {
  BackendJob,
  MediaSubmissionPayload,
  RuntimeApi,
  RuntimeUiState,
  VisualizerPayloadRow,
} from './runtimeApi'

export class MockRuntimeApi implements RuntimeApi {
  private jobs: BackendJob[] = []
  private rows: VisualizerPayloadRow[] = [
    {
      sentence_text: 'Although she had been warned several times, she still chose to ignore the evidence, which eventually led to a costly mistake that could have been avoided.',
      tree: {
        node_id: 's1',
        type: 'Sentence',
        content: 'Although she had been warned several times, she still chose to ignore the evidence, which eventually led to a costly mistake that could have been avoided.',
        cefr_level: 'B2',
        translations: ['Хотя ее несколько раз предупреждали, она все же решила игнорировать доказательства, что в итоге привело к дорогостоящей ошибке, которой можно было избежать.'],
        linguistic_notes: ['Complex sentence with subordinate and relative clauses.'],
        children: [
          {
            node_id: 'p1',
            type: 'Phrase',
            phraseType: 'Verb Phrase',
            content: 'still chose to ignore the evidence',
            tense: 'Past Simple',
            children: [
              {
                node_id: 'w1',
                type: 'Word',
                content: 'chose',
                part_of_speech: 'verb',
                children: [],
              },
              {
                node_id: 'w2',
                type: 'Word',
                content: 'to',
                part_of_speech: 'preposition',
                children: [],
              },
              {
                node_id: 'w3',
                type: 'Word',
                content: 'ignore',
                part_of_speech: 'verb',
                children: [],
              },
              {
                node_id: 'w4',
                type: 'Word',
                content: 'the',
                part_of_speech: 'article',
                children: [],
              },
              {
                node_id: 'w5',
                type: 'Word',
                content: 'evidence',
                part_of_speech: 'noun',
                children: [],
              },
            ],
          },
          {
            node_id: 'w6',
            type: 'Word',
            content: 'she',
            part_of_speech: 'pronoun',
            children: [],
          },
          {
            node_id: 'p2',
            type: 'Phrase',
            phraseType: 'Prepositional Phrase',
            content: 'which eventually led to a costly mistake',
            children: [
              {
                node_id: 'w7',
                type: 'Word',
                content: 'led',
                part_of_speech: 'verb',
                children: [],
              },
              {
                node_id: 'w8',
                type: 'Word',
                content: 'to',
                part_of_speech: 'preposition',
                children: [],
              },
              {
                node_id: 'w9',
                type: 'Word',
                content: 'a',
                part_of_speech: 'article',
                children: [],
              },
              {
                node_id: 'w10',
                type: 'Word',
                content: 'costly mistake',
                part_of_speech: 'noun',
                children: [],
              },
            ],
          },
        ],
      },
    },
  ]

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

  async getVisualizerPayload(): Promise<VisualizerPayloadRow[]> {
    return this.rows
  }

  async applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
  }): Promise<{ status: 'ok' | 'error'; message: string }> {
    const targetRow = this.rows.find((r) => r.sentence_text === input.sentenceText)
    if (!targetRow) {
      return { status: 'error', message: 'Sentence not found.' }
    }
    if (input.fieldPath !== 'content') {
      return { status: 'error', message: 'Mock supports only `content` field path.' }
    }
    const stack = [targetRow.tree]
    while (stack.length > 0) {
      const node = stack.pop()!
      if (node.node_id === input.nodeId) {
        node.content = input.newValue
        const words = input.newValue.trim().split(/\s+/).filter(Boolean)
        const directLeafChildren = node.children.filter((c) => c.children.length === 0)
        if (directLeafChildren.length === words.length && words.length > 0) {
          directLeafChildren.forEach((child, idx) => {
            child.content = words[idx]
          })
        }
        return { status: 'ok', message: 'Edit applied.' }
      }
      for (const child of node.children) stack.push(child)
    }
    return { status: 'error', message: 'node_id not found.' }
  }
}

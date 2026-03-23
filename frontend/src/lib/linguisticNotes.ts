import type { VisualizerNode } from '../api/runtimeApi'

export type LinguisticNotesLevels = {
  elementary: string
  intermediate: string
  advanced: string
}

export function normalizeLinguisticNotes(input: VisualizerNode['linguistic_notes'] | unknown): LinguisticNotesLevels {
  const out: LinguisticNotesLevels = { elementary: '', intermediate: '', advanced: '' }
  if (Array.isArray(input)) {
    const notes = input.map((v) => String(v || '').trim()).filter(Boolean)
    if (notes.length >= 3) {
      out.elementary = notes[0]
      out.intermediate = notes[1]
      out.advanced = notes[2]
    } else if (notes.length === 2) {
      out.elementary = notes[0]
      out.intermediate = notes[1]
    } else if (notes.length === 1) {
      out.intermediate = notes[0]
    }
    return out
  }
  if (input && typeof input === 'object') {
    const src = input as Record<string, unknown>
    out.elementary = String(src.elementary || '').trim()
    out.intermediate = String(src.intermediate || '').trim()
    out.advanced = String(src.advanced || '').trim()
  }
  return out
}

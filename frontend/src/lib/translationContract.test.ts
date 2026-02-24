import { listAlternativeTranslations, resolveNodeTranslation } from './translationContract'
import type { VisualizerNode } from '../api/runtimeApi'

function baseNode(): VisualizerNode {
  return {
    node_id: 'n1',
    type: 'Sentence',
    content: 'She trusted him.',
    tense: '',
    linguistic_notes: [],
    part_of_speech: 'sentence',
    linguistic_elements: [],
  }
}

describe('resolveNodeTranslation', () => {
  it('prefers selected provider from translations map', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        backend_m2m100: { text: 'Она доверяла ему.' },
        gpt: { text: 'Она ему доверяла.' },
      },
    }
    expect(resolveNodeTranslation(node)).toBe('Она ему доверяла.')
  })

  it('falls back to backend provider', () => {
    const nodeWithBackend: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'deepl',
      translations: {
        backend_m2m100: { text: 'Она доверяла ему.' },
      },
    }
    expect(resolveNodeTranslation(nodeWithBackend)).toBe('Она доверяла ему.')

    const nodeWithoutTranslations: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'deepl',
    }
    expect(resolveNodeTranslation(nodeWithoutTranslations)).toBe('-')
  })

  it('respects explicit preferred provider parameter', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        backend_m2m100: { text: 'Backend translation' },
        deepl: { text: 'DeepL translation' },
        gpt: { text: 'GPT translation' },
      },
    }
    expect(resolveNodeTranslation(node, 'deepl')).toBe('DeepL translation')
  })

  it('lists alternative translations except active one', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        backend_m2m100: { text: 'Backend translation' },
        gpt: { text: 'GPT translation' },
        deepl: { text: 'DeepL translation' },
      },
    }
    expect(listAlternativeTranslations(node)).toEqual([
      { provider: 'backend_m2m100', text: 'Backend translation' },
      { provider: 'deepl', text: 'DeepL translation' },
    ])
  })
})

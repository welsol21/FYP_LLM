import { listAlternativeTranslations, resolveNodeTranslation, resolveNodeTranslationVariant } from './translationContract'
import type { VisualizerNode } from '../api/runtimeApi'

function baseNode(): VisualizerNode {
  return {
    node_id: 'n1',
    type: 'Sentence',
    content: 'She trusted him.',
    tense: '',
    linguistic_notes: [],
    part_of_speech: 'sentence',
    translations: {
      m2m100: { text: 'Она доверяла ему.' },
    },
    linguistic_elements: [],
  }
}

describe('resolveNodeTranslation', () => {
  it('prefers selected provider from translations map', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        m2m100: { text: 'Она доверяла ему.' },
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
        m2m100: { text: 'Она доверяла ему.' },
      },
    }
    expect(resolveNodeTranslation(nodeWithBackend)).toBe('Она доверяла ему.')

    const nodeWithoutTranslations: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'deepl',
      translations: {
        m2m100: { text: '' },
      },
    }
    expect(resolveNodeTranslation(nodeWithoutTranslations)).toBe('-')
  })

  it('respects explicit preferred provider parameter', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        m2m100: { text: 'Backend translation' },
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
        m2m100: { text: 'Backend translation' },
        gpt: { text: 'GPT translation' },
        deepl: { text: 'DeepL translation' },
      },
    }
    expect(listAlternativeTranslations(node)).toEqual([
      { provider: 'm2m100', text: 'Backend translation' },
      { provider: 'deepl', text: 'DeepL translation' },
    ])
  })

  it('keeps alternative provider even when text is the same', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'm2m100',
      translations: {
        m2m100: { text: 'Она пришла к нему к утрам.' },
        gpt: { text: 'Она пришла к нему к утрам.' },
      },
    }
    expect(listAlternativeTranslations(node)).toEqual([
      { provider: 'gpt', text: 'Она пришла к нему к утрам.' },
    ])
  })

  it('does not duplicate same provider aliases after normalization of separators', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'm2m100',
      translations: {
        m2m100: { text: 'Она пришла к нему к утрам.' },
        'm2m100 ': { text: 'Она пришла к нему к утрам.' },
      },
    }
    expect(listAlternativeTranslations(node)).toEqual([])
  })
})

describe('resolveNodeTranslationVariant', () => {
  it('returns provider and text for selected translation', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        m2m100: { text: 'Backend translation' },
        gpt: { text: 'GPT translation' },
      },
    }
    expect(resolveNodeTranslationVariant(node)).toEqual({
      provider: 'gpt',
      text: 'GPT translation',
    })
  })

  it('falls back to first non-empty provider when preferred and canonical are empty', () => {
    const node: VisualizerNode = {
      ...baseNode(),
      active_translation_provider: 'gpt',
      translations: {
        m2m100: { text: '' },
        deepl: { text: 'DeepL translation' },
      },
    }
    expect(resolveNodeTranslationVariant(node)).toEqual({
      provider: 'deepl',
      text: 'DeepL translation',
    })
  })
})

import type { VisualizerNode } from '../api/runtimeApi'
import { alignNodeTranslationsFromSentence, fillMissingNodeTranslations } from './translationAlignment'

function makeNode(input: Partial<VisualizerNode> & Pick<VisualizerNode, 'node_id' | 'content'>): VisualizerNode {
  return {
    node_id: input.node_id,
    type: input.type || 'Node',
    content: input.content,
    tense: input.tense || '',
    linguistic_notes: input.linguistic_notes || [],
    part_of_speech: input.part_of_speech || 'noun',
    translations: input.translations || {},
    source_span: input.source_span,
    linguistic_elements: input.linguistic_elements || [],
    active_translation_provider: input.active_translation_provider,
    sentence_idx: input.sentence_idx,
    sentence_hash: input.sentence_hash,
  }
}

describe('translationAlignment', () => {
  it('aligns child node translations from sentence translation by source_span', () => {
    const sentence = 'The voice of reason.'
    const root = makeNode({
      node_id: 'root',
      content: sentence,
      part_of_speech: 'sentence',
      source_span: { start: 0, end: sentence.length },
      linguistic_elements: [
        makeNode({
          node_id: 'n1',
          content: 'The voice',
          source_span: { start: 0, end: 9 },
          part_of_speech: 'noun_phrase',
        }),
      ],
    })

    const result = alignNodeTranslationsFromSentence({
      root,
      sentenceSourceText: sentence,
      sentenceTranslatedText: 'Голос разума.',
      provider: 'm2m100',
    })

    expect(result.alignedCount).toBeGreaterThanOrEqual(1)
    expect(root.translations.m2m100?.text).toBe('Голос разума.')
    expect(root.linguistic_elements[0].translations.m2m100?.text).toContain('Голос')
  })

  it('returns missing texts when a node cannot be aligned by source_span', () => {
    const root = makeNode({
      node_id: 'root',
      content: 'She trusted him.',
      part_of_speech: 'sentence',
      source_span: { start: 0, end: 16 },
      linguistic_elements: [
        makeNode({
          node_id: 'n1',
          content: 'trusted',
          part_of_speech: 'verb',
        }),
      ],
    })

    const result = alignNodeTranslationsFromSentence({
      root,
      sentenceSourceText: 'She trusted him.',
      sentenceTranslatedText: 'Она доверяла ему.',
      provider: 'm2m100',
    })

    expect(result.missingNodeTexts).toContain('trusted')
  })

  it('fills missing node translations from fallback map', () => {
    const root = makeNode({
      node_id: 'root',
      content: 'She trusted him.',
      part_of_speech: 'sentence',
      linguistic_elements: [
        makeNode({
          node_id: 'n1',
          content: 'trusted',
          part_of_speech: 'verb',
        }),
      ],
    })

    const filled = fillMissingNodeTranslations({
      root,
      provider: 'm2m100',
      translationMap: { trusted: 'доверяла' },
    })

    expect(filled).toBe(1)
    expect(root.linguistic_elements[0].translations.m2m100?.text).toBe('доверяла')
  })
})

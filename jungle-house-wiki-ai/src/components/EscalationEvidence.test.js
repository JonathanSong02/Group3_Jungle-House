import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { escalationReasonKey, previousResponseEvidence } from '../utils/escalationEvidence.js';

test('T01/T03/T09/T10: system narratives and unknown records are never inferred to be AI answers', () => {
  const notes = [
    ['staff_requested_escalation', 'Staff reviewed the suggested Knowledge Base articles and asked for a team lead.', 'requested'],
    ['staff_not_satisfied_escalated', 'Staff said this previous AI answer was not correct.', 'rejected'],
    ['repeated_invalid_input', 'Could not understand.', 'invalidInput'],
    ['repeated_failed_answer', 'Still unresolved.', 'repeated'],
    ['system_error', 'An internal system error occurred while generating the answer.', 'systemError'],
    ['fallback', 'Fallback narrative', 'unconfirmed'],
    ['unexpected_historical_source', '<script>unknown record</script>', 'unknownReason'],
  ];
  for (const [ai_source, ai_answer, reason] of notes) {
    const evidence = previousResponseEvidence({ ai_source, ai_answer });
    assert.equal(evidence.answer, '');
    assert.equal(evidence.note, ai_answer);
    assert.equal(escalationReasonKey(ai_source), `esc.evidence.${reason}`);
  }
  assert.equal(previousResponseEvidence({ ai_source: 'ai_provider_answer', ai_answer: notes[0][1] }).answer, '');
  assert.equal(previousResponseEvidence({}).answer, '');
  assert.equal(previousResponseEvidence({ ai_source: 'ai_provider_answer', ai_answer: 'A recorded answer.' }).answer, 'A recorded answer.');
});

test('T02/T04/T12/T13: three-language evidence UI keeps excerpts separate and safely renders legacy records', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' });
  try {
    const { default: Evidence } = await server.ssrLoadModule('/src/components/EscalationEvidence.jsx');
    const { LanguageProvider } = await server.ssrLoadModule('/src/i18n/LanguageContext.jsx');
    const ticket = { ai_source: 'staff_requested_escalation', ai_answer: 'Staff reviewed the suggested Knowledge Base articles and asked for a team lead.',
      conversation_context: { provenance: 'client_supplied_unverified', messages: [
        { role: 'user', content: 'Synthetic staff question' },
        { role: 'assistant', content: 'First actual assistant reply' },
        { role: 'assistant', content: 'A later clarification' },
      ] } };
    for (const [language, previous, requested] of [
      ['en', 'Previous AI Response', 'Staff requested human assistance'],
      ['zh', '先前 AI 回复', '员工主动请求'],
      ['ms', 'Jawapan AI Sebelumnya', 'Kakitangan meminta bantuan manusia'],
    ]) {
      globalThis.window = { localStorage: { getItem: () => language } };
      const render = (value) => renderToStaticMarkup(React.createElement(LanguageProvider, null, React.createElement(Evidence, { ticket: value })));
      const html = render(ticket);
      const previousSection = html.split('</section>')[0];
      assert(html.includes(previous));
      assert(html.includes(requested));
      assert(!previousSection.includes(ticket.ai_answer));
      assert(!previousSection.includes('A later clarification')); // Do not choose the last assistant message.
      assert(!html.includes('esc.evidence.'));
      const legacy = render({ ai_source: 'old_custom', ai_answer: '<script>unsafe</script>' });
      assert(legacy.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
      assert(!legacy.includes('<script>'));
      assert(!render({}).includes('undefined'));
    }
    assert(previousResponseEvidence(ticket).hasAssistantExcerpts);
  } finally {
    await server.close();
    delete globalThis.window;
  }
});

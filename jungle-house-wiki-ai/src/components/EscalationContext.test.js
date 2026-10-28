import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('discussion component renders three languages, escapes excerpts and filters links', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' });
  try {
    const { default: EscalationContext } = await server.ssrLoadModule('/src/components/EscalationContext.jsx');
    const { LanguageProvider } = await server.ssrLoadModule('/src/i18n/LanguageContext.jsx');
    const context = { provenance: 'client_supplied_unverified', trigger_question: 'iPad cabinet locked', description: 'Spring → ST3', reason: 'fallback', omitted_messages: 2,
      messages: [{ role: 'user', content: '<script>untrusted</script>', timestamp: null, attachments: ['/static/uploads/chat/123_ipad.png', 'https://example.invalid/unsafe'] }] };
    for (const [language, label] of [['en', 'Relevant discussion'], ['zh', '相关讨论'], ['ms', 'Perbincangan berkaitan']]) {
      globalThis.window = { localStorage: { getItem: () => language } };
      const html = renderToStaticMarkup(React.createElement(LanguageProvider, null, React.createElement(EscalationContext, { context })));
      assert(html.includes(label));
      assert(html.includes('&lt;script&gt;untrusted&lt;/script&gt;'));
      assert(!html.includes('<script>untrusted'));
      assert(!html.includes('https://example.invalid/unsafe'));
      assert(html.includes('/static/uploads/chat/123_ipad.png'));
    }
    assert(renderToStaticMarkup(React.createElement(EscalationContext, { context: null })).includes('No discussion snapshot'));
    globalThis.window = { localStorage: { getItem: () => 'en' } };
    const detailed = { ...context, messages: [
      { role: 'user', content: 'Original ice payment question' }, { role: 'assistant', content: 'First answer' },
      { role: 'user', content: 'Intermediate situation' }, { role: 'assistant', content: 'Intermediate explanation' },
      { role: 'user', content: 'I mean receiving two packs of ice' }, { role: 'assistant', content: 'Answer about two packs' },
      { role: 'user', content: 'Not what I want' }, { role: 'assistant', content: 'Please explain your situation' },
      { role: 'user', content: 'Still need help' },
    ] };
    const html = renderToStaticMarkup(React.createElement(LanguageProvider, null, React.createElement(EscalationContext, { context: detailed })));
    const preview = html.split('<details>')[0];
    assert(preview.includes('Original ice payment question'));
    assert(preview.includes('I mean receiving two packs of ice'));
    assert(preview.includes('Answer about two packs'));
    assert(!preview.includes('Intermediate situation'));
    assert(html.includes('Intermediate situation'));
    assert(html.includes('View saved relevant messages'));
  } finally {
    await server.close();
    delete globalThis.window;
  }
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('discussion component renders three languages, escapes excerpts and filters links', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
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
    assert.equal(renderToStaticMarkup(React.createElement(EscalationContext, { context: null })), '');
  } finally {
    await server.close();
    delete globalThis.window;
  }
});

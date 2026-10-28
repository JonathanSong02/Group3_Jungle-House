import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('standard question requires human confirmation and renders three languages', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' });
  try {
    const { default: StandardQuestionField } = await server.ssrLoadModule('/src/components/StandardQuestionField.jsx');
    const { LanguageProvider } = await server.ssrLoadModule('/src/i18n/LanguageContext.jsx');
    for (const [language, label] of [['en', 'Standard question / article title'], ['zh', '标准问题／文章标题'], ['ms', 'Soalan standard / tajuk artikel']]) {
      globalThis.window = { localStorage: { getItem: () => language } };
      const html = renderToStaticMarkup(React.createElement(LanguageProvider, null, React.createElement(StandardQuestionField, {
        value: 'How much should staff pay when receiving two packs of ice?', confirmed: false, onChange() {}, onConfirm() {},
      })));
      assert(html.includes(label));
      assert(html.includes('maxLength="255"'));
      assert(html.includes('required=""'));
      assert(html.includes('type="checkbox"'));
      assert(!html.includes('checked=""'));
    }
  } finally {
    await server.close();
    delete globalThis.window;
  }
});

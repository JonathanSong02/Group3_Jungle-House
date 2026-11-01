import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { translations } from '../i18n/translations.js';

test('chat storage failures appear once with the correct title, separate from upload rejection', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' });
  try {
    const { default: ChatStatusNotice } = await server.ssrLoadModule('/src/components/ChatStatusNotice.jsx');
    for (const language of ['en', 'zh', 'ms']) {
      const t = (key) => translations[language][key];
      const render = (props) => renderToStaticMarkup(React.createElement(ChatStatusNotice, { t, ...props }));
      const html = render({ storageError: t('chat.memoryUnavailable'), onRetry() {} });
      assert.equal((html.match(/role="alert"/g) || []).length, 1);
      assert(html.includes(t('chat.storageUnavailableTitle')));
      assert(html.includes(t('chat.retryConnection')));
      assert(!html.includes(t('chat.uploadRejected')));
      assert(render({ uploadError: 'Invalid file' }).includes(t('chat.uploadRejected')));
      assert(render({ storageError: 'Unavailable', retrying: true, onRetry() {} }).includes('disabled'));
      assert.equal(render({}), '');
    }
  } finally { await server.close(); }
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { escalationMetadata, normalizeEscalationResponse, escalationErrorInfo } from './escalationResponse.js';
import { translations } from '../i18n/translations.js';

const t = (key, vars = {}) => translations.en[key].replace(/\{(\w+)\}/g, (_, name) => String(vars[name]));
// Exercise the actual local response builder without importing Chat/Auth/API or a browser.
const source = readFileSync(new URL('../pages/Chat.jsx', import.meta.url), 'utf8');
const builderSource = source.slice(source.indexOf('function buildAiMessage('), source.indexOf('\nfunction extractLatestSopContext('));
const buildAiMessage = new Function('escalationMetadata', 'normalizeEscalationResponse', `${builderSource}; return buildAiMessage;`)(escalationMetadata, normalizeEscalationResponse);

test('T11/T14: returned ticket ID and safe snapshot status survive all response types', () => {
  for (const response of [
    { type: 'text', answer: 'Normal answer' },
    { type: 'sop', steps: [{ step_number: 1, content: 'Step' }] },
    { type: 'options', options: [{ label: 'Article' }] },
  ]) {
    const message = buildAiMessage({ ...response, escalation_id: 123, escalation_context_status: 'saved', escalation_context_saved: true }, t);
    assert.equal(message.escalation_id, 123);
    assert.equal(message.escalation_context_status, 'saved');
    assert.equal(message.escalation_context_saved, true);
    assert.equal(message.escalation_context_warning, false);
  }
  for (const id of [undefined, null, 0, -1, true, 'not-an-id', '', 1.5, '1e3', Number.MAX_SAFE_INTEGER + 1]) {
    assert(!Object.hasOwn(buildAiMessage({ answer: 'Answer', escalation_id: id }, t), 'escalation_id'));
  }
  assert.equal(escalationMetadata({ escalation_id: '42' }).escalation_id, 42);
  assert(!JSON.stringify(escalationMetadata({ escalation_id: 1, escalation_context_status: 'SELECT secret', escalation_context_warning: 'private details' })).includes('secret'));
  assert(!JSON.stringify(escalationMetadata({ escalation_id: 1, escalation_context_warning: 'private details' })).includes('private details'));
});

test('T06/T07: absent snapshot differs from rejected or failed storage', () => {
  assert.equal(buildAiMessage({ escalation_id: 1, escalation_context_saved: false, escalation_context_status: 'not_provided' }, t).escalation_context_warning, false);
  for (const status of ['invalid_context', 'schema_missing', 'storage_permission_denied', 'storage_unavailable']) {
    assert.equal(buildAiMessage({ escalation_id: 1, escalation_context_saved: false, escalation_context_status: status }, t).escalation_context_warning, true);
  }
});

test('T11: HTTP errors retain a real ticket without becoming success or exposing raw errors', () => {
  const result = escalationErrorInfo({ response: { status: 500, data: { escalation_id: 123, escalation_context_saved: false,
    escalation_context_status: 'storage_unavailable', message: 'SQL/private path/credentials' } } }, t);
  assert.equal(result.escalation_id, 123);
  assert(result.escalation_request_failed);
  assert(result.text.includes('request failed'));
  assert(result.text.includes('#123'));
  assert(!JSON.stringify(result).includes('credentials'));
  assert(!Object.hasOwn(escalationErrorInfo({ response: { data: { escalation_id: null } } }, t), 'escalation_id'));
  assert.equal(escalationErrorInfo({ response: { status: 401, data: { code: 'SESSION_EXPIRED' } } }, t), null);
});

test('T12/T14: failed inserts never render success, and normal chat remains unchanged', () => {
  for (const language of ['en', 'zh', 'ms']) {
    const translate = (key) => translations[language][key];
    for (const data of [
      { escalation_id: null, escalation: true, reply: 'I have escalated it' },
      { source: 'escalation_save_failed', answer: 'technical backend terminal message' },
    ]) {
      const message = buildAiMessage(data, translate);
      assert.equal(message.text, translate('chat.ticketSaveFailed'));
      assert.equal(message.answer, message.text);
      assert.equal(message.fallback_message, message.text);
      assert.equal(message.escalation_required, false);
      assert(!Object.hasOwn(message, 'escalation_id'));
    }
  }
  const normal = { type: 'text', answer: 'Normal SOP answer', confidence: 0.9, context: { title: 'Opening' } };
  assert.equal(normalizeEscalationResponse(normal, t), normal);
  const result = buildAiMessage(normal, t);
  assert.equal(result.text, normal.answer);
  assert.equal(result.confidence, 0.9);
  assert.deepEqual(result.context, normal.context);
});

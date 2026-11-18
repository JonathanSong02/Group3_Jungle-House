import test from 'node:test';
import assert from 'node:assert/strict';
import { imageReferencesForQuestion } from './imageAttachmentContext.js';

const a = 'a'.repeat(64);
const b = 'b'.repeat(64);
test('image follow-up keeps opaque references after JSON persistence in three languages', () => {
  const messages = JSON.parse(JSON.stringify([{ sender: 'user', attachment_refs: [a] }]));
  for (const question of ['Where should I put it?', '这个应该放哪里？', 'Di mana saya simpan itu?']) {
    assert.deepEqual(imageReferencesForQuestion(messages, question), [a]);
  }
});
test('new chat and independent text topics never reuse personal images', () => {
  assert.deepEqual(imageReferencesForQuestion([], 'Where should I put it?'), []);
  assert.deepEqual(imageReferencesForQuestion([{ sender: 'user', attachment_refs: [a] }], 'staff belongings'), []);
  assert.deepEqual(imageReferencesForQuestion([{ sender: 'user', attachment_refs: [a] }], 'Explain this attendance policy'), []);
});
test('multiple images remain ambiguous and raw paths or assistant IDs are ignored', () => {
  const messages = [{ sender: 'user', attachment_refs: [a, '/static/private.jpg'] },
    { sender: 'user', attachment_refs: [b] }, { sender: 'ai', attachment_refs: ['c'.repeat(64)] }];
  assert.deepEqual(imageReferencesForQuestion(messages, 'What about this image?'), [b, a]);
});

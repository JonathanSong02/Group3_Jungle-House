import test from 'node:test';
import assert from 'node:assert/strict';
import { imageFailureDetails } from './imageServiceError.js';

test('schema failures retain operational source and safe support reference without AI confidence', () => {
  const details = imageFailureDetails({ response: { data: {
    source: 'image_service_unavailable', code: 'IMAGE_SCHEMA_NOT_READY', error_id: 'a'.repeat(16),
  } } }, true);
  assert.equal(details.source, 'image_service_unavailable');
  assert.equal(details.error_code, 'IMAGE_SCHEMA_NOT_READY');
  assert.equal(details.error_id, 'a'.repeat(16));
  assert.equal(details.confidence_kind, 'not_calibrated');
  assert.equal(details.error, true);
});
test('image timeouts stay non-calibrated while text errors retain existing behavior', () => {
  assert.equal(imageFailureDetails({}, true).source, 'frontend_request_error');
  assert.equal(imageFailureDetails({}, true).confidence_kind, 'not_calibrated');
  assert.deepEqual(imageFailureDetails({}, false), {});
});
test('unexpected server fields cannot introduce sources or unsafe support identifiers', () => {
  const details = imageFailureDetails({ response: { data: {
    source: 'wiki_article_database', code: '<script>', error_id: 'private-file-path',
  } } }, true);
  assert.equal(details.source, 'frontend_request_error');
  assert.equal(details.error_code, undefined);
  assert.equal(details.error_id, undefined);
});

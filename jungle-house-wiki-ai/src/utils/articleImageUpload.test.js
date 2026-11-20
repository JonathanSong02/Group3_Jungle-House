import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  ARTICLE_IMAGE_UPLOAD_PATH,
  ArticleUploadError,
  MAX_ARTICLE_IMAGE_BYTES,
  buildInlineFileHtml,
  checkArticleImage,
  createArticleImageUploader,
  createRecentFileFilter,
  uploadErrorKind,
  uploadErrorMessage,
} from './articleImageUpload.js';

const MESSAGES = {
  'article.upload.type': 'This file type is not allowed.',
  'article.upload.size': 'The image is too large.',
  'article.upload.session': 'Your session has expired. Please sign in again.',
  'article.upload.forbidden': 'You do not have permission to upload images.',
  'article.upload.failed': 'Image upload failed. Please try again.',
};
const t = (key) => MESSAGES[key] || key;
const zh = (key) => `zh:${key}`;
const image = (name = 'photo.jpg', type = 'image/jpeg', size = 1000) =>
  new File([new Uint8Array(size)], name, { type, lastModified: 1700000000000 });
const httpError = (status, data = {}) => Object.assign(new Error(`status ${status}`), { response: { status, data } });

function harness({ post } = {}) {
  const calls = { post: [], inserted: [], uploaded: [], errors: [], started: 0, restored: 0, saved: 0, cursorAt: null };
  const editor = {
    s: {
      insertCursorAtPoint: (x, y) => { calls.cursorAt = [x, y]; },
      save: () => { calls.saved += 1; },
      restore: () => { calls.restored += 1; },
    },
  };
  const uploader = createArticleImageUploader({
    post: post || (async (path, data) => {
      calls.post.push({ path, files: data.getAll('attachments').map((f) => f.name) });
      return { data: { files: [`/static/uploads/articles/${calls.post.length}_x.jpg`], error: 0, msg: 'success' } };
    }),
    getContext: () => ({
      t, language: 'en', editor,
      insertHtml: (html) => calls.inserted.push(html),
      onStart: () => { calls.started += 1; },
      onUploaded: (url) => calls.uploaded.push(url),
      onError: (text) => calls.errors.push(text),
    }),
  });
  return { uploader, calls };
}

test('the helper has no backend address in it', () => {
  const source = readFileSync(new URL('./articleImageUpload.js', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /railway|localhost|127\.0\.0\.1|https?:\/\//i);
  assert.equal(ARTICLE_IMAGE_UPLOAD_PATH, '/articles/upload-image');
});

test('only images the backend accepts, up to 8 MB', () => {
  for (const [name, type] of [['a.png', 'image/png'], ['a.jpg', 'image/jpeg'], ['a.gif', 'image/gif'], ['a.webp', 'image/webp'],
    ['a.heic', 'image/heic'], ['IMG_1.HEIC', ''], ['scan.jpg', '']]) {
    assert.equal(checkArticleImage(image(name, type)), null, name);
  }
  for (const [name, type] of [['notes.txt', 'text/plain'], ['a.pdf', 'application/pdf'], ['a.svg', 'image/svg+xml'],
    ['a.bmp', 'image/bmp'], ['noextension', '']]) {
    assert.equal(checkArticleImage(image(name, type)), 'type', name);
  }
  assert.equal(checkArticleImage(image('big.jpg', 'image/jpeg', MAX_ARTICLE_IMAGE_BYTES + 1)), 'size');
  assert.equal(checkArticleImage(image('ok.jpg', 'image/jpeg', MAX_ARTICLE_IMAGE_BYTES)), null);
  assert.equal(checkArticleImage(image('empty.jpg', 'image/jpeg', 0)), 'failed');
  assert.equal(checkArticleImage(null), 'failed');
});

test('server and network errors become clear messages, in the selected language', () => {
  const fake = httpError(400, { code: 'INVALID_UPLOAD', error: 1, msg: 'The uploaded file does not match its file type.' });
  assert.equal(uploadErrorKind(fake), 'type');
  assert.equal(uploadErrorMessage(fake, t, 'en'), 'The uploaded file does not match its file type.');   // the server's own words
  assert.equal(uploadErrorMessage(fake, zh, 'zh'), 'zh:article.upload.type');
  assert.equal(uploadErrorKind(httpError(400, { msg: 'Unsupported file type. Please upload PNG, JPG.' })), 'type');
  assert.equal(uploadErrorKind(httpError(401, { code: 'SESSION_EXPIRED' })), 'session');
  assert.equal(uploadErrorKind(httpError(403, { code: 'CSRF_INVALID' })), 'session');
  assert.equal(uploadErrorKind(httpError(403, { code: 'FORBIDDEN' })), 'forbidden');
  assert.equal(uploadErrorKind(httpError(413, { reply: 'This file is too large.' })), 'size');
  assert.equal(uploadErrorKind(new Error('Network Error')), 'failed');
  assert.equal(uploadErrorMessage(httpError(401), t, 'en'), MESSAGES['article.upload.session']);
  assert.equal(uploadErrorMessage(httpError(500, { message: 'Traceback (most recent call last): ...' }), t, 'en'), MESSAGES['article.upload.failed']);
  assert.equal(uploadErrorMessage(httpError(400, { msg: 'Traceback\n  File "app.py"' }), t, 'en'), MESSAGES['article.upload.failed']);
  assert.equal(uploadErrorMessage(new ArticleUploadError('size'), t, 'en'), MESSAGES['article.upload.size']);
  assert.equal(uploadErrorMessage(new ArticleUploadError('type'), zh, 'zh'), 'zh:article.upload.type');
});

test('the inserted HTML is the same as before', () => {
  assert.equal(buildInlineFileHtml('/static/uploads/articles/1_a.png', 'pasted-image.png', true),
    '<p><img src="/static/uploads/articles/1_a.png" alt="pasted-image.png" /></p>');
  assert.equal(buildInlineFileHtml('/static/uploads/articles/1_r.pdf', 'Report.pdf', false),
    '<p><a href="#" class="article-inline-file" data-file-url="/static/uploads/articles/1_r.pdf" data-file-name="Report.pdf">📄 Report.pdf <span class="article-inline-file-caret">▾</span></a></p>');
  assert.equal(buildInlineFileHtml('/x.png', 'a"b<c>.png', true), '<p><img src="/x.png" alt="a&quot;b&lt;c&gt;.png" /></p>');
});

test('the same file twice in one action is let through once', () => {
  let clock = 0;
  const isNew = createRecentFileFilter(3000, () => clock);
  const file = image();
  assert.equal(isNew(file), true);
  assert.equal(isNew(file), false);
  assert.equal(isNew(image('other.jpg')), true);
  clock = 3001;
  assert.equal(isNew(file), true);
});

test('upload goes through the given shared client to the relative path and inserts the image', async () => {
  const { uploader, calls } = harness();
  const urls = await uploader.uploadAndInsert([image('a.jpg'), image('b.jpg')]);
  assert.deepEqual(calls.post, [{ path: '/articles/upload-image', files: ['a.jpg'] }, { path: '/articles/upload-image', files: ['b.jpg'] }]);
  assert.deepEqual(urls, ['/static/uploads/articles/1_x.jpg', '/static/uploads/articles/2_x.jpg']);
  assert.deepEqual(calls.inserted, [
    '<p><img src="/static/uploads/articles/1_x.jpg" alt="a.jpg" /></p>',
    '<p><img src="/static/uploads/articles/2_x.jpg" alt="b.jpg" /></p>',
  ]);
  assert.deepEqual(calls.uploaded, urls);
  assert.equal(calls.started, 1);
  assert.deepEqual(calls.errors, []);
});

test('refused files are never sent, and nothing is inserted', async () => {
  const { uploader, calls } = harness();
  await uploader.uploadAndInsert([image('notes.txt', 'text/plain'), image('big.jpg', 'image/jpeg', MAX_ARTICLE_IMAGE_BYTES + 1)]);
  assert.deepEqual(calls.post, []);
  assert.deepEqual(calls.inserted, []);
  assert.deepEqual(calls.errors, [MESSAGES['article.upload.type'], MESSAGES['article.upload.size']]);
});

test('server refusals and an expired session show one clear message and insert nothing', async () => {
  for (const [error, expected] of [
    [httpError(400, { error: 1, msg: 'The uploaded file does not match its file type.' }), 'The uploaded file does not match its file type.'],
    [httpError(401, { code: 'SESSION_EXPIRED' }), MESSAGES['article.upload.session']],
    [httpError(413, {}), MESSAGES['article.upload.size']],
    [new Error('Network Error'), MESSAGES['article.upload.failed']],
  ]) {
    const { uploader, calls } = harness({ post: async () => { throw error; } });
    await uploader.uploadAndInsert([image()]);
    assert.deepEqual(calls.inserted, []);
    assert.deepEqual(calls.errors, [expected]);
  }
  const { uploader, calls } = harness({ post: async () => ({ data: { files: [], error: 1, msg: 'No valid image file was uploaded.' } }) });
  await uploader.uploadAndInsert([image()]);
  assert.deepEqual(calls.errors, ['No valid image file was uploaded.']);
});

test('paste: images are taken over, text and HTML are left to the editor', async () => {
  const { uploader, calls } = harness();
  const flags = { prevented: false, stopped: false };
  const handled = uploader.handlePasteCapture({
    clipboardData: { items: [{ kind: 'string', type: 'text/html' }, { kind: 'file', type: 'image/png', getAsFile: () => image('pasted.png', 'image/png') }] },
    preventDefault: () => { flags.prevented = true; }, stopPropagation: () => { flags.stopped = true; },
  });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(handled, true);
  assert.deepEqual(flags, { prevented: true, stopped: true });
  assert.equal(calls.post.length, 1);

  const text = { prevented: false };
  assert.equal(uploader.handlePasteCapture({ clipboardData: { items: [{ kind: 'string', type: 'text/plain' }] },
    preventDefault: () => { text.prevented = true; }, stopPropagation() {} }), false);
  assert.equal(text.prevented, false);
});

test('drop: files are taken over and inserted where they were dropped; dragging text is left alone', async () => {
  const { uploader, calls } = harness();
  const flags = { prevented: false, stopped: false };
  uploader.handleDropCapture({
    dataTransfer: { files: [image('dropped.jpg')] }, clientX: 120, clientY: 340,
    preventDefault: () => { flags.prevented = true; }, stopPropagation: () => { flags.stopped = true; },
  });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(flags, { prevented: true, stopped: true });
  assert.deepEqual(calls.cursorAt, [120, 340]);
  assert.equal(calls.saved, 1);
  assert.equal(calls.restored, 1);              // back to the drop point before inserting
  assert.equal(calls.inserted.length, 1);

  const text = { prevented: false };
  assert.equal(uploader.handleDropCapture({ dataTransfer: { files: [] }, preventDefault: () => { text.prevented = true; }, stopPropagation() {} }), false);
  assert.equal(text.prevented, false);

  const over = { prevented: false };
  uploader.handleDragOverCapture({ dataTransfer: { types: ['Files'] }, preventDefault: () => { over.prevented = true; } });
  assert.equal(over.prevented, true);
  const overText = { prevented: false };
  uploader.handleDragOverCapture({ dataTransfer: { types: ['text/plain'] }, preventDefault: () => { overText.prevented = true; } });
  assert.equal(overText.prevented, false);
});

test('toolbar: Jodit hands the files over, no backend address and no request of its own', async () => {
  const { uploader, calls } = harness();
  const options = uploader.joditUploaderOptions();
  assert.equal(options.url, '');
  assert.equal(options.withCredentials, undefined);
  assert.equal(typeof options.customUploadFunction, 'function');
  const form = new FormData();
  form.append('path', '');
  form.append('attachments', image('toolbar.jpg'), 'toolbar.jpg');
  let progress = null;
  const answer = await options.customUploadFunction(form, (value) => { progress = value; });
  assert.deepEqual(answer, { error: 0, files: [] });       // already inserted; Jodit only closes its popup
  assert.equal(options.isSuccess(answer), true);
  assert.deepEqual(options.process(answer).files, []);
  assert.equal(progress, 100);
  assert.deepEqual(calls.post, [{ path: '/articles/upload-image', files: ['toolbar.jpg'] }]);
  assert.equal(calls.restored, 1);                           // the cursor the image button saved
  assert.equal(calls.inserted.length, 1);
});

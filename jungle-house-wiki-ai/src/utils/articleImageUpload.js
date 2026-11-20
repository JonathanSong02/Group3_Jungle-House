// One upload path for every way of adding an image in the article editor (Add / Edit Article):
// paste (Ctrl+V), drag-and-drop, and the toolbar's Image -> Upload.
//
// Every upload goes through the shared API client that the page passes in as `post` (services/api.js), to
// the relative path below. So the session cookie and the CSRF token are handled exactly like every other
// request, and there is no backend address in this file. Jodit's own uploader is only used for its toolbar
// UI (file picker, camera on phones); its network call is replaced by customUploadFunction.

export const ARTICLE_IMAGE_UPLOAD_PATH = '/articles/upload-image';
// The backend refuses requests larger than 8 MB (MAX_CONTENT_LENGTH); checked here first to save the upload.
export const MAX_ARTICLE_IMAGE_BYTES = 8 * 1024 * 1024;

// The image types the backend accepts for articles (it also checks the real file content).
const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp', 'image/heic', 'image/heif']);
const IMAGE_NAME = /\.(png|jpe?g|gif|webp|heic|heif)$/i;
export const ARTICLE_IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'heif'];

const MESSAGE_KEYS = {
  type: 'article.upload.type',
  size: 'article.upload.size',
  session: 'article.upload.session',
  forbidden: 'article.upload.forbidden',
  failed: 'article.upload.failed',
};
const SESSION_CODES = new Set(['SESSION_EXPIRED', 'AUTH_REQUIRED', 'ACCOUNT_INACTIVE', 'CSRF_INVALID']);
const TYPE_MESSAGE = /unsupported file type|does not match its file type|not a valid supported file/i;

export class ArticleUploadError extends Error {
  constructor(kind, serverMessage = '') {
    super(`article image upload: ${kind}`);
    this.kind = kind;
    this.serverMessage = serverMessage;
  }
}

const escapeHtml = (value = '') =>
  String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

// The HTML the editor has always inserted for an image or a file (unchanged).
export function buildInlineFileHtml(url, name, isImage) {
  if (isImage) {
    return `<p><img src="${escapeHtml(url)}" alt="${escapeHtml(name)}" /></p>`;
  }
  // href is deliberately "#", not the real file URL: some browser extensions (e.g. Adobe Acrobat)
  // auto-intercept navigation to links that look like PDF URLs before our own click handler gets a chance
  // to run. The real URL lives in data-file-url and is only ever read by our own JS.
  return `<p><a href="#" class="article-inline-file" data-file-url="${escapeHtml(url)}" data-file-name="${escapeHtml(name)}">📄 ${escapeHtml(name)} <span class="article-inline-file-caret">▾</span></a></p>`;
}

// null when the file may be uploaded, otherwise 'type' or 'size'.
export function checkArticleImage(file) {
  if (!file || typeof file.size !== 'number') return 'failed';
  const type = String(file.type || '').toLowerCase();
  const isImage = type ? IMAGE_TYPES.has(type) : IMAGE_NAME.test(String(file.name || ''));
  if (!isImage) return 'type';
  if (file.size > MAX_ARTICLE_IMAGE_BYTES) return 'size';
  if (file.size === 0) return 'failed';
  return null;
}

function serverText(data) {
  const text = data && (data.msg || data.message);
  return typeof text === 'string' && text.length <= 300 && !/\n|traceback/i.test(text) ? text : '';
}

// Which kind of failure an error from the shared client (or this file) is.
export function uploadErrorKind(error) {
  if (error instanceof ArticleUploadError) return error.kind;
  const status = error?.response?.status;
  const data = error?.response?.data || {};
  if (status === 401 || SESSION_CODES.has(data.code)) return 'session';
  if (status === 403) return 'forbidden';
  if (status === 413) return 'size';
  if (status === 400 && TYPE_MESSAGE.test(serverText(data))) return 'type';
  return 'failed';
}

// The message to show, in the selected language. In English the server's own message for a refused file is
// shown when it gave one (a short fixed text, never a stack trace).
export function uploadErrorMessage(error, t, language = 'en') {
  const kind = uploadErrorKind(error);
  const fromServer = error instanceof ArticleUploadError
    ? error.serverMessage
    : (error?.response?.status === 400 ? serverText(error?.response?.data) : '');
  if (language === 'en' && fromServer && (kind === 'type' || kind === 'failed')) return fromServer;
  return t(MESSAGE_KEYS[kind] || MESSAGE_KEYS.failed);
}

// True the first time a file is seen within `windowMs`. Stops one action (for example a drop that also
// arrives as a paste) from uploading the same image twice.
export function createRecentFileFilter(windowMs = 3000, now = () => Date.now()) {
  const seen = new Map();
  return (file) => {
    const time = now();
    for (const [key, at] of seen) if (time - at > windowMs) seen.delete(key);
    const key = [file?.name, file?.size, file?.type, file?.lastModified].join('|');
    if (seen.has(key)) return false;
    seen.set(key, time);
    return true;
  };
}

/**
 * post(path, formData) -> Promise<{ data }>   the shared API client's post
 * getContext() -> { t, language, editor, insertHtml(html), onStart(), onUploaded(url), onError(text) }
 *   read at the moment of each upload, so the latest language and editor are used.
 */
export function createArticleImageUploader({ post, getContext }) {
  const isNew = createRecentFileFilter();

  async function uploadOne(file) {
    const problem = checkArticleImage(file);
    if (problem) throw new ArticleUploadError(problem);

    const data = new FormData();
    data.append('attachments', file, file.name || `pasted-image-${Date.now()}.png`);
    // No Content-Type header: the browser must set the multipart boundary itself.
    let response;
    try {
      response = await post(ARTICLE_IMAGE_UPLOAD_PATH, data);
    } catch (error) {
      throw error instanceof ArticleUploadError ? error : Object.assign(new ArticleUploadError(uploadErrorKind(error),
        error?.response?.status === 400 ? serverText(error?.response?.data) : ''), { cause: error });
    }
    const url = response?.data?.files?.[0];
    if (!url || response?.data?.error) {
      throw new ArticleUploadError('failed', serverText(response?.data));
    }
    return url;
  }

  // Uploads each new file one after another and inserts it. Each failure is shown once. Returns the URLs.
  async function uploadAndInsert(files, { restoreSelection = false } = {}) {
    const context = getContext();
    const fresh = Array.from(files || []).filter((file) => file && isNew(file));
    const uploaded = [];
    if (!fresh.length) {
      if (restoreSelection) context.editor?.s?.restore?.();
      return uploaded;
    }
    context.onStart?.();
    for (const file of fresh) {
      try {
        const url = await uploadOne(file);
        uploaded.push({ url, name: file.name || 'image.png' });
      } catch (error) {
        const latest = getContext();
        latest.onError?.(uploadErrorMessage(error, latest.t, latest.language));
      }
    }
    const latest = getContext();
    if (restoreSelection) latest.editor?.s?.restore?.();     // back to where the image should go
    uploaded.forEach(({ url, name }) => {
      latest.insertHtml(buildInlineFileHtml(url, name, true));
      latest.onUploaded?.(url);
    });
    return uploaded.map(({ url }) => url);
  }

  // Paste (Ctrl+V): images only. Text and copied HTML are left to the editor exactly as before.
  function handlePasteCapture(event) {
    const items = Array.from(event?.clipboardData?.items || []);
    const files = items
      .filter((item) => item.kind === 'file' && String(item.type || '').startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter(Boolean);
    if (!files.length) return false;
    event.preventDefault();
    event.stopPropagation();
    uploadAndInsert(files);
    return true;
  }

  // Dragging files over the editor: allow the drop. Dragging text inside the editor is left alone.
  function handleDragOverCapture(event) {
    if (Array.from(event?.dataTransfer?.types || []).includes('Files')) {
      event.preventDefault();
    }
  }

  // Drag-and-drop of files: insert where they are dropped. Text dragged inside the editor is left alone.
  function handleDropCapture(event) {
    const files = Array.from(event?.dataTransfer?.files || []);
    if (!files.length) return false;
    event.preventDefault();
    event.stopPropagation();
    const editor = getContext().editor;
    let placed = false;
    try {
      if (editor?.s?.insertCursorAtPoint && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
        editor.s.insertCursorAtPoint(event.clientX, event.clientY);
        editor.s.save();          // keep the drop point while the upload runs
        placed = true;
      }
    } catch {
      placed = false;             // fall back to the current cursor position
    }
    uploadAndInsert(files, { restoreSelection: placed });
    return true;
  }

  // Jodit's uploader options for the toolbar's Image -> Upload (and its file picker / camera on phones).
  // There is no url: Jodit hands the chosen files to customUploadFunction, which uses the path above.
  function joditUploaderOptions() {
    return {
      url: '',
      insertImageAsBase64URI: false,
      imagesExtensions: ARTICLE_IMAGE_EXTENSIONS,
      filesVariableName: () => 'attachments',
      customUploadFunction: async (formData, showProgress) => {
        const files = typeof formData?.getAll === 'function'
          ? formData.getAll('attachments').filter((value) => value && typeof value === 'object' && 'size' in value)
          : [];
        try {
          // The image button saved the cursor before opening its popup; insert there.
          await uploadAndInsert(files, { restoreSelection: true });
        } finally {
          showProgress?.(100);
        }
        // Already inserted (and any error already shown): Jodit only closes its popup.
        return { error: 0, files: [] };
      },
      isSuccess: () => true,
      getMessage: () => '',
      process: () => ({ files: [], path: '', baseurl: '', isImages: [] }),
      defaultHandlerSuccess: () => {},
      defaultHandlerError: () => {},
    };
  }

  return { uploadAndInsert, handlePasteCapture, handleDragOverCapture, handleDropCapture, joditUploaderOptions };
}

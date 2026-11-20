import { useEffect, useMemo, useRef, useState } from 'react';
import JoditEditor from 'jodit-react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { removePageLevelTags } from '../../utils/safeHtml';
import { useLanguage } from '../../i18n/LanguageContext';
import { translateServerMessage } from '../../i18n/serverMessages';
import { buildInlineFileHtml, createArticleImageUploader } from '../../utils/articleImageUpload';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

const acceptedFileTypes =
  'image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp,image/svg+xml,.pdf,.doc,.docx';

// Splits a translated sentence on its {button} placeholder so the button name stays bold.
function withBoldButton(text, buttonLabel) {
  const [before, after = ''] = String(text).split('{button}');
  return (
    <>
      {before}
      <strong>{buttonLabel}</strong>
      {after}
    </>
  );
}

export default function AddArticle() {
  const navigate = useNavigate();
  const editorRef = useRef(null);
  const fileInputRef = useRef(null);
  const { t, tOr, language } = useLanguage();
  const [editorPlaceholder] = useState(() => t('article.form.contentPlaceholder'));

  const [form, setForm] = useState({
    title: '',
    category: 'SOP',
    sub_category: '',
    link: '',
    content: '',
  });

  const [attachments, setAttachments] = useState([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [insertingIndex, setInsertingIndex] = useState(null);

  // URLs of files uploaded/pasted during THIS still-unsaved session (not
  // yet part of any saved article). Tracked in a ref, not state, since it's
  // pure bookkeeping that should never trigger a re-render on its own.
  // Cleaned up (deleted from Railway) if the user removes one from the
  // editor, cancels, or navigates away without saving -- cleared without
  // deleting once the article actually saves, since these become real
  // referenced files at that point.
  const sessionUploadedUrlsRef = useRef([]);

  const cleanupUploadedUrls = (urls) => {
    const list = (urls || []).filter(Boolean);
    if (!list.length) return;

    api.post('/articles/cleanup-uploads', { urls: list }).catch((error) => {
      console.error('Cleanup unused uploads error:', error);
    });
  };

  // Best-effort: catches navigating away (sidebar link, browser back) without
  // ever clicking Save or Cancel. Both of those already clear the ref
  // themselves, so this only ever has something to do when neither ran.
  useEffect(() => {
    return () => {
      if (sessionUploadedUrlsRef.current.length) {
        cleanupUploadedUrls(sessionUploadedUrlsRef.current);
      }
    };
  }, []);

  // Paste, drag-and-drop and the toolbar's Image -> Upload all use ONE upload
  // path: the shared API client (relative /api, session cookie and CSRF token
  // like every other request). See utils/articleImageUpload.js. Its context
  // (language, editor, where to insert) is refreshed after every render.
  const uploadContextRef = useRef(null);
  const imageUploader = useMemo(
    () => createArticleImageUploader({
      post: (path, data) => api.post(path, data),
      getContext: () => uploadContextRef.current,
    }),
    []
  );

  const editorConfig = useMemo(
    () => ({
      readonly: false,
      height: 430,
      placeholder: editorPlaceholder,
      toolbarAdaptive: false,
      toolbarSticky: false,
      showCharsCounter: false,
      showWordsCounter: false,
      showXPathInStatusbar: false,
      askBeforePasteHTML: false,
      // Stored or pasted HTML must not add <base>/<meta>/<link>/<style>/<script>
      // to the page while it is being edited (see utils/safeHtml.js). Jodit's
      // own cleaning (event attributes, javascript: links) stays on.
      cleanHTML: { sanitizer: removePageLevelTags },
      askBeforePasteFromWord: false,
      defaultActionOnPaste: 'insert_as_html',
      // Keeps the editor a drop target. Dropped and pasted image files are
      // uploaded by the page's capture handlers (see the editor wrapper).
      enableDragAndDropFileToEditor: true,
      buttons: [
        'source',
        '|',
        'bold',
        'italic',
        'underline',
        'strikethrough',
        '|',
        'fontsize',
        'paragraph',
        'brush',
        '|',
        'ul',
        'ol',
        '|',
        'table',
        'link',
        'image',
        '|',
        'left',
        'center',
        'right',
        'justify',
        '|',
        'undo',
        'redo',
        'eraser',
      ],
      // Toolbar Image -> Upload: Jodit shows its file picker (camera/photos
      // on phones); the upload itself goes through the shared client.
      uploader: imageUploader.joditUploaderOptions(),
    }),
    [imageUploader, editorPlaceholder]
  );

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event) => {
    const selectedFiles = Array.from(event.target.files || []);

    if (selectedFiles.length === 0) {
      return;
    }

    setAttachments((prev) => [...prev, ...selectedFiles]);

    // Important: reset input so user can select the same file again if needed
    event.target.value = '';
  };

  const removeAttachment = (indexToRemove) => {
    setAttachments((prev) =>
      prev.filter((_, index) => index !== indexToRemove)
    );
  };

  const formatFileSize = (bytes) => {
    if (!bytes) {
      return t('article.form.selectedFile');
    }

    const sizeInMb = bytes / (1024 * 1024);

    if (sizeInMb >= 1) {
      return `${sizeInMb.toFixed(2)} MB`;
    }

    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  };

  const isImageFile = (fileName = '') =>
    /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(fileName);

  // Places the given HTML at the editor's current cursor position so staff
  // can position an attached file anywhere inside the article body, instead
  // of it always landing in the fixed "Attachments" list at the bottom.
  const insertHtmlIntoContent = (html) => {
    const editor = editorRef.current;

    if (editor?.selection?.insertHTML) {
      editor.selection.insertHTML(html);
      setForm((prev) => ({ ...prev, content: editor.value ?? prev.content }));
    } else {
      setForm((prev) => ({ ...prev, content: `${prev.content}${html}` }));
    }
  };

  // Uploads a not-yet-saved selected file immediately (same endpoint the
  // rich-text editor's own image button uses) and drops the returned HTML
  // into the content at the cursor, then removes it from the pending
  // "Selected files" list since it's now saved and referenced from content.
  const insertAttachmentIntoContent = async (index) => {
    const file = attachments[index];
    if (!file) return;

    try {
      setInsertingIndex(index);
      setMessage('');

      const uploadData = new FormData();
      uploadData.append('attachments', file);

      // Deliberately no explicit Content-Type header -- axios/the browser
      // must generate it themselves for FormData, since it has to include
      // a unique multipart boundary string. Setting it manually here
      // (as this used to) silently corrupts every uploaded file, because
      // the server can no longer tell where one field/file ends and the
      // next begins.
      const response = await api.post('/articles/upload-image', uploadData);

      const fileUrl = response.data?.files?.[0];

      if (!fileUrl || response.data?.error) {
        throw new Error(translateServerMessage(t, response.data?.msg) || t('article.msg.uploadFailed'));
      }

      insertHtmlIntoContent(
        buildInlineFileHtml(fileUrl, file.name, isImageFile(file.name))
      );
      sessionUploadedUrlsRef.current.push(fileUrl);
      removeAttachment(index);
    } catch (error) {
      console.error('Insert attachment into content error:', error);
      setMessage(
        translateServerMessage(t, error.response?.data?.msg || error.message) || t('article.msg.insertFailed')
      );
    } finally {
      setInsertingIndex(null);
    }
  };

  // Upload errors: the page's message box and the editor's own message.
  const showUploadError = (text) => {
    setMessage(text);
    editorRef.current?.message?.error?.(text, 6000);
  };

  // What the shared upload helper reads at the moment of an upload.
  useEffect(() => {
    uploadContextRef.current = {
      t,
      language,
      get editor() {
        return editorRef.current;
      },
      insertHtml: insertHtmlIntoContent,
      onStart: () => setMessage(''),
      onUploaded: (url) => sessionUploadedUrlsRef.current.push(url),
      onError: showUploadError,
    };
  });

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.title.trim() || !form.content.trim()) {
      setMessage(t('article.msg.required'));
      return;
    }

    try {
      setSaving(true);
      setMessage('');

      const formData = new FormData();
      formData.append('title', form.title.trim());
      formData.append('category', form.category.trim());
      formData.append('sub_category', form.sub_category.trim());
      formData.append('link', form.link.trim());
      formData.append('content', form.content.trim());

      attachments.forEach((file) => {
        formData.append('attachments', file);
      });

      // No manual Content-Type here either -- same reasoning as above.
      await api.post('/articles', formData);

      // The article saved successfully, so every session-uploaded file is
      // now genuinely referenced -- clear the tracking list WITHOUT
      // deleting anything (that's the opposite of Cancel above).
      sessionUploadedUrlsRef.current = [];

      navigate('/admin/content');
    } catch (error) {
      console.error('Create article error:', error);
      setMessage(translateServerMessage(t, error.response?.data?.message) || t('article.msg.createFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={t('article.form.addTitle')}
        subtitle={t('article.form.addSubtitle')}
      />

      <section className="card-like top-gap-sm">
        <form onSubmit={handleSubmit} className="stack-gap">
          {message && (
            <div className="card-like danger-soft">
              <p>{translateServerMessage(t, message)}</p>
            </div>
          )}

          <div className="form-grid">
            <label>
              {t('article.form.title')}
              <input
                name="title"
                value={form.title}
                onChange={handleChange}
                placeholder={t('article.form.titlePlaceholder')}
              />
            </label>

            <label>
              {t('article.form.category')}
              <select
                name="category"
                value={form.category}
                onChange={handleChange}
              >
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {language === 'en' ? category : tOr(`cat.${category}`, category)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t('article.form.subCategory')}
              <input
                name="sub_category"
                value={form.sub_category}
                onChange={handleChange}
                placeholder={t('article.form.subCategoryPlaceholder')}
              />
            </label>

            <label>
              {t('article.form.link')}
              <input
                name="link"
                value={form.link}
                onChange={handleChange}
                placeholder={t('article.form.linkPlaceholder')}
              />
            </label>

            <div className="full-width article-attachment-panel">
              <div className="article-attachment-top">
                <div>
                  <h3>{t('article.form.attachTitle')}</h3>
                  <p>
                    {t('article.form.attachHintCreate')}
                  </p>
                </div>

                <button
                  type="button"
                  className="secondary-btn attachment-add-btn"
                  onClick={openFilePicker}
                >
                  {t('article.form.addFile')}
                </button>
              </div>

              <input
                ref={fileInputRef}
                className="hidden-file-input"
                type="file"
                accept={acceptedFileTypes}
                multiple
                onChange={handleFileChange}
              />

              {attachments.length > 0 && (
                <div className="attachment-group">
                  <div className="attachment-group-header">
                    <p className="attachment-group-title">
                      {t('article.form.selectedFiles', { n: attachments.length })}
                    </p>

                    <button
                      type="button"
                      className="secondary-btn attachment-clear-btn"
                      onClick={() => setAttachments([])}
                    >
                      {t('article.form.clearAll')}
                    </button>
                  </div>

                  <div className="attachment-list">
                    {attachments.map((file, index) => (
                      <div
                        className="attachment-card"
                        key={`${file.name}-${file.size}-${index}`}
                      >
                        <span className="attachment-icon">
                          {isImageFile(file.name) ? t('article.form.badgeImage') : t('article.form.badgeFile')}
                        </span>

                        <div className="attachment-info">
                          <strong>{file.name}</strong>
                          <span>{formatFileSize(file.size)}</span>
                        </div>

                        <button
                          type="button"
                          className="secondary-btn attachment-view-btn"
                          disabled={insertingIndex === index}
                          onClick={() => insertAttachmentIntoContent(index)}
                        >
                          {insertingIndex === index ? t('article.form.inserting') : t('article.form.insert')}
                        </button>

                        <button
                          type="button"
                          className="attachment-remove-btn"
                          onClick={() => removeAttachment(index)}
                        >
                          {t('common.remove')}
                        </button>
                      </div>
                    ))}
                  </div>

                  <p className="attachment-hint">
                    {withBoldButton(t('article.form.insertTipNew'), t('article.form.insert'))}
                  </p>
                </div>
              )}

              {attachments.length === 0 && (
                <div className="empty-attachment-box">
                  {withBoldButton(t('article.form.noFile'), t('article.form.addFile'))}
                </div>
              )}
            </div>

            <label className="full-width">
              {t('article.form.content')}

              <div
                className="article-rich-editor"
                // Captured here, before Jodit's own listeners, so a pasted or
                // dropped image is uploaded exactly once through the shared
                // helper. Text and HTML pastes/drags still go to Jodit.
                onPasteCapture={imageUploader.handlePasteCapture}
                onDragOverCapture={imageUploader.handleDragOverCapture}
                onDropCapture={imageUploader.handleDropCapture}
              >
                <JoditEditor
                  ref={editorRef}
                  value={form.content}
                  config={editorConfig}
                  onBlur={(newContent) =>
                    setForm((prev) => ({
                      ...prev,
                      content: newContent,
                    }))
                  }
                  onChange={(newContent) => {
                    // If the editor's content just changed such that a
                    // still-unsaved uploaded/pasted file's URL is no longer
                    // anywhere in it, the user just removed it from the
                    // body -- clean it up immediately instead of leaving it
                    // orphaned on Railway until the page is closed.
                    const stillPresent = [];
                    const removed = [];

                    sessionUploadedUrlsRef.current.forEach((url) => {
                      (newContent.includes(url) ? stillPresent : removed).push(url);
                    });

                    if (removed.length) {
                      cleanupUploadedUrls(removed);
                    }

                    sessionUploadedUrlsRef.current = stillPresent;

                    setForm((prev) => ({
                      ...prev,
                      content: newContent,
                    }));
                  }}
                />
              </div>
            </label>
          </div>

          <div className="button-group">
            <button
              type="button"
              className="secondary-btn"
              onClick={() => {
                cleanupUploadedUrls(sessionUploadedUrlsRef.current);
                sessionUploadedUrlsRef.current = [];
                navigate('/admin/content');
              }}
            >
              {t('common.cancel')}
            </button>

            <button
              type="submit"
              className="primary-btn narrow-btn"
              disabled={saving}
            >
              {saving ? t('article.form.creating') : t('article.form.create')}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
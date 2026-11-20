import { useEffect, useMemo, useRef, useState } from 'react';
import JoditEditor from 'jodit-react';
import { useNavigate, useParams } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { cleanStoredEditorHtml, removePageLevelTags } from '../../utils/safeHtml';
import { useLanguage } from '../../i18n/LanguageContext';
import { translateServerMessage } from '../../i18n/serverMessages';
import { buildInlineFileHtml, createArticleImageUploader } from '../../utils/articleImageUpload';

// 'Notion' = synced from Notion but not categorized yet; listed so such an
// article shows its real category here instead of appearing as 'SOP'.
const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice', 'Notion'];
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

export default function EditArticle() {
  const { id } = useParams();
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
  const [currentAttachments, setCurrentAttachments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [insertingIndex, setInsertingIndex] = useState(null);

  // URLs of NEW files uploaded/pasted during this edit session that were
  // never part of the article when it loaded. Deliberately separate from
  // the article's already-existing images: removing one of THOSE and
  // clicking Save is already handled by the backend's own before/after
  // diff on update, and clicking Cancel must never touch them at all.
  // This ref only ever tracks brand-new files from this session, tracked
  // in a ref (not state) since it's pure bookkeeping, not render data.
  const sessionUploadedUrlsRef = useRef([]);

  const cleanupUploadedUrls = (urls) => {
    const list = (urls || []).filter(Boolean);
    if (!list.length) return;

    api.post('/articles/cleanup-uploads', { urls: list }).catch((error) => {
      console.error('Cleanup unused uploads error:', error);
    });
  };

  // Best-effort: catches navigating away (sidebar link, browser back)
  // without ever clicking Save or Cancel. Both of those already clear the
  // ref themselves, so this only has something to do when neither ran.
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

  useEffect(() => {
    const fetchArticle = async () => {
      try {
        setLoading(true);
        setMessage('');

        const response = await api.get(`/articles/${id}`);
        const article = response.data;

        setForm({
          title: article.title || '',
          category: article.category || 'SOP',
          sub_category: article.sub_category || '',
          link: article.link || '',
          // Jodit writes the first value straight into the page before any of
          // its own cleaning runs, so stored content is cleaned here first
          // (event attributes, script URLs, page-level tags). Inline styles,
          // classes and the rest of the authoring HTML are kept.
          content: cleanStoredEditorHtml(article.content || ''),
        });

        let parsedAttachments = [];

        if (Array.isArray(article.image_files)) {
          parsedAttachments = article.image_files;
        } else if (article.image_files) {
          try {
            parsedAttachments = JSON.parse(article.image_files);
          } catch (error) {
            console.error('Parse image_files error:', error);
            parsedAttachments = [];
          }
        }

        // The legacy single attachment_url column mirrors image_files[0],
        // but fall back to it if image_files is empty so old articles that
        // predate multi-file support still show their attached file here.
        if (
          parsedAttachments.length === 0 &&
          article.attachment_url
        ) {
          parsedAttachments = [{
            url: article.attachment_url,
            type: article.attachment_type,
          }];
        }

        setCurrentAttachments(parsedAttachments);
      } catch (error) {
        console.error('Fetch article error:', error);
        setMessage(error.response?.data?.message || 'Failed to load article.');
      } finally {
        setLoading(false);
      }
    };

    fetchArticle();
  }, [id]);

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

    event.target.value = '';
  };

  const removeAttachment = (indexToRemove) => {
    setAttachments((prev) =>
      prev.filter((_, index) => index !== indexToRemove)
    );
  };

  const removeCurrentAttachment = (indexToRemove) => {
    setCurrentAttachments((prev) =>
      prev.filter((_, index) => index !== indexToRemove)
    );
  };

  const getAttachmentFileName = (file) => {
    if (file?.name) return file.name;
    const fileUrl = file?.url || file?.file_url || file?.path || file;
    const rawName = String(fileUrl || '').split('/').pop() || t('article.form.attachmentFile');
    // Stored filenames are prefixed with a millisecond timestamp
    // (e.g. "1731999999999_Opening SOP.pdf") to keep them unique on disk.
    return rawName.replace(/^\d+_/, '');
  };

  const getFileUrl = (file) => {
    const fileUrl = file?.url || file?.file_url || file?.path || file;
    if (!fileUrl) return '';
    if (fileUrl.startsWith('http://') || fileUrl.startsWith('https://')) {
      return fileUrl;
    }
    // Deliberately left relative, never an absolute backend URL. The
    // backend now requires a logged-in session for
    // /static/ files, and that session cookie is SameSite=Lax -- it's only
    // sent for same-origin requests. A relative path resolves against this
    // page's own Vercel origin, which Vercel's rewrite forwards to Railway
    // while still carrying the cookie; an absolute Railway URL is a
    // different origin, so the cookie never attaches and the image request
    // comes back 401 instead of the file.
    return fileUrl.startsWith('/') ? fileUrl : `/${fileUrl}`;
  };

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
  // "New selected files" list since it's now saved and referenced from content.
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

  // Existing attachments already have a saved URL, so this just drops them
  // into the content at the cursor and removes them from the separate
  // Attachments list so the file isn't shown in both places.
  const insertExistingAttachmentIntoContent = (index) => {
    const file = currentAttachments[index];
    if (!file) return;

    const fileName = getAttachmentFileName(file);
    insertHtmlIntoContent(
      buildInlineFileHtml(getFileUrl(file), fileName, isImageFile(fileName))
    );
    removeCurrentAttachment(index);
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
      formData.append('existing_attachments', JSON.stringify(currentAttachments));

      attachments.forEach((file) => {
        formData.append('attachments', file);
      });

      // No manual Content-Type here either -- same reasoning as above.
      await api.put(`/articles/${id}`, formData);

      // The article saved successfully, so every session-uploaded file is
      // now genuinely referenced -- clear the tracking list WITHOUT
      // deleting anything (that's the opposite of Cancel above). Any
      // pre-existing images the user removed during this edit are cleaned
      // up separately, by the backend's own before/after diff.
      sessionUploadedUrlsRef.current = [];

      navigate('/admin/content');
    } catch (error) {
      console.error('Update article error:', error);
      setMessage(translateServerMessage(t, error.response?.data?.message) || t('article.msg.updateFailed'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <section className="card-like">
        <p className="muted">{t('article.form.loading')}</p>
      </section>
    );
  }

  return (
    <div>
      <PageHeader
        title={t('article.form.editTitle')}
        subtitle={t('article.form.editSubtitle')}
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
              />
            </label>

            <label>
              {t('article.form.link')}
              <input
                name="link"
                value={form.link}
                onChange={handleChange}
              />
            </label>

            <div className="full-width article-attachment-panel">
              <div className="article-attachment-top">
                <div>
                  <h3>{t('article.form.attachReplaceTitle')}</h3>
                  <p>
                    {t('article.form.attachHintSave')}
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

              {currentAttachments.length > 0 && (
                <div className="attachment-group">
                  <p className="attachment-group-title">{t('article.form.existingFiles')}</p>

                  <div className="attachment-list">
                    {currentAttachments.map((file, index) => {
                      const fileName = getAttachmentFileName(file);

                      return (
                        <div
                          className="attachment-card current"
                          key={`${fileName}-${index}`}
                        >
                          <span className="attachment-icon">
                            {isImageFile(fileName) ? t('article.form.badgeImage') : t('article.form.badgeFile')}
                          </span>

                          <div className="attachment-info">
                            <strong>{fileName}</strong>
                            <span>{t('article.form.existingFile')}</span>
                          </div>

                          <a
                            className="secondary-btn attachment-view-btn"
                            href={getFileUrl(file)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {t('common.view')}
                          </a>

                          <button
                            type="button"
                            className="secondary-btn attachment-view-btn"
                            onClick={() => insertExistingAttachmentIntoContent(index)}
                          >
                            {t('article.form.insert')}
                          </button>

                          <button
                            type="button"
                            className="attachment-remove-btn"
                            onClick={() => removeCurrentAttachment(index)}
                          >
                            {t('common.remove')}
                          </button>
                        </div>
                      );
                    })}
                  </div>

                  <p className="attachment-hint">
                    {withBoldButton(t('article.form.insertTipExisting'), t('article.form.insert'))}
                  </p>
                </div>
              )}

              {attachments.length > 0 && (
                <div className="attachment-group">
                  <div className="attachment-group-header">
                    <p className="attachment-group-title">
                      {t('article.form.newSelectedFiles', { n: attachments.length })}
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
                </div>
              )}

              {attachments.length === 0 && currentAttachments.length === 0 && (
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
                    // If a still-unsaved-this-session uploaded/pasted
                    // file's URL is no longer anywhere in the new content,
                    // the user just removed it from the body -- clean it
                    // up immediately instead of leaving it orphaned on
                    // Railway until the page is closed. Existing (already
                    // saved) images are untouched here; those are handled
                    // by the backend's own before/after diff on Save.
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
                // Only ever deletes files uploaded/pasted THIS session --
                // the article's pre-existing images are never touched by
                // Cancel, exactly as required.
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
              {saving ? t('article.form.saving') : t('article.form.saveChanges')}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
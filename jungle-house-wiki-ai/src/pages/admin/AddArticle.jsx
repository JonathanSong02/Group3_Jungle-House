import { useEffect, useMemo, useRef, useState } from 'react';
import JoditEditor from 'jodit-react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { removePageLevelTags } from '../../utils/safeHtml';
import { useLanguage } from '../../i18n/LanguageContext';
import { buildInlineFileHtml, createArticleImageUploader } from '../../utils/articleImageUpload';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

const acceptedFileTypes =
  'image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp,image/svg+xml,.pdf,.doc,.docx';

export default function AddArticle() {
  const navigate = useNavigate();
  const editorRef = useRef(null);
  const fileInputRef = useRef(null);
  const { t, language } = useLanguage();

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
      placeholder: 'Write article content here...',
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
    [imageUploader]
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
      return 'Selected file';
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
        throw new Error(response.data?.msg || 'Failed to upload file.');
      }

      insertHtmlIntoContent(
        buildInlineFileHtml(fileUrl, file.name, isImageFile(file.name))
      );
      sessionUploadedUrlsRef.current.push(fileUrl);
      removeAttachment(index);
    } catch (error) {
      console.error('Insert attachment into content error:', error);
      setMessage(
        error.response?.data?.msg || error.message || 'Failed to insert file into content.'
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
      setMessage('Title and content are required.');
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
      setMessage(error.response?.data?.message || 'Failed to create article.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Add Article"
        subtitle="Create a new knowledge base article."
      />

      <section className="card-like top-gap-sm">
        <form onSubmit={handleSubmit} className="stack-gap">
          {message && (
            <div className="card-like danger-soft">
              <p>{message}</p>
            </div>
          )}

          <div className="form-grid">
            <label>
              Article Title *
              <input
                name="title"
                value={form.title}
                onChange={handleChange}
                placeholder="Enter article title"
              />
            </label>

            <label>
              Category *
              <select
                name="category"
                value={form.category}
                onChange={handleChange}
              >
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Sub Category
              <input
                name="sub_category"
                value={form.sub_category}
                onChange={handleChange}
                placeholder="Example: Opening SOP"
              />
            </label>

            <label>
              Notion / Reference Link
              <input
                name="link"
                value={form.link}
                onChange={handleChange}
                placeholder="Paste reference link if available"
              />
            </label>

            <div className="full-width article-attachment-panel">
              <div className="article-attachment-top">
                <div>
                  <h3>Attach Image or File</h3>
                  <p>
                    Click add to select one or more images/files. You can click
                    the button again to add more before creating the article.
                  </p>
                </div>

                <button
                  type="button"
                  className="secondary-btn attachment-add-btn"
                  onClick={openFilePicker}
                >
                  + Add Image / File
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
                      Selected files ({attachments.length})
                    </p>

                    <button
                      type="button"
                      className="secondary-btn attachment-clear-btn"
                      onClick={() => setAttachments([])}
                    >
                      Clear All
                    </button>
                  </div>

                  <div className="attachment-list">
                    {attachments.map((file, index) => (
                      <div
                        className="attachment-card"
                        key={`${file.name}-${file.size}-${index}`}
                      >
                        <span className="attachment-icon">
                          {isImageFile(file.name) ? 'IMG' : 'FILE'}
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
                          {insertingIndex === index ? 'Inserting...' : 'Insert into Content'}
                        </button>

                        <button
                          type="button"
                          className="attachment-remove-btn"
                          onClick={() => removeAttachment(index)}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>

                  <p className="attachment-hint">
                    Tip: use <strong>Insert into Content</strong> to place a file
                    exactly where you want it in the article body. Files left
                    here will show in the general Attachments list instead.
                  </p>
                </div>
              )}

              {attachments.length === 0 && (
                <div className="empty-attachment-box">
                  No file selected yet. Click <strong>+ Add Image / File</strong>{' '}
                  to attach one or more files.
                </div>
              )}
            </div>

            <label className="full-width">
              Article Content *

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
              Cancel
            </button>

            <button
              type="submit"
              className="primary-btn narrow-btn"
              disabled={saving}
            >
              {saving ? 'Creating...' : 'Create Article'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
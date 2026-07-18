import { useEffect, useMemo, useRef, useState } from 'react';
import JoditEditor from 'jodit-react';
import { useNavigate, useParams } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];
const acceptedFileTypes =
  'image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp,image/svg+xml,.pdf,.doc,.docx';
const API_BASE_URL = 'https://group3jungle-house-production.up.railway.app';

export default function EditArticle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const editorRef = useRef(null);
  const fileInputRef = useRef(null);

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
      askBeforePasteFromWord: false,
      defaultActionOnPaste: 'insert_as_html',
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
      uploader: {
        url: `${API_BASE_URL}/api/articles/upload-image`,
        insertImageAsBase64URI: false,
        filesVariableName: () => 'attachments',
        withCredentials: false,
        // Backend returns { files, path, baseurl, error, msg } instead of Jodit's
        // default { success, data: { files, baseurl, isImages, messages } } shape,
        // so isSuccess/getMessage/process must be told how to read it.
        isSuccess: (resp) => !resp.error,
        getMessage: (resp) => resp.msg || 'Upload failed.',
        process: (resp) => ({
          files: resp.files || [],
          path: resp.path || '',
          baseurl: resp.baseurl || '',
          isImages: (resp.files || []).map(() => true),
        }),
      },
    }),
    []
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
          content: article.content || '',
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
    const rawName = String(fileUrl || '').split('/').pop() || 'Attachment file';
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
    return `${API_BASE_URL}${fileUrl.startsWith('/') ? '' : '/'}${fileUrl}`;
  };

  const escapeHtml = (value = '') =>
    String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  const buildInlineFileHtml = (url, name, isImage) => {
    if (isImage) {
      return `<p><img src="${url}" alt="${escapeHtml(name)}" /></p>`;
    }

    // href is deliberately "#", not the real file URL: some browser
    // extensions (e.g. Adobe Acrobat) auto-intercept navigation to links
    // that look like PDF URLs before our own click handler gets a chance
    // to run. The real URL lives in data-file-url and is only ever read
    // by our own JS, so there's nothing for an extension to hijack.
    return `<p><a href="#" class="article-inline-file" data-file-url="${url}" data-file-name="${escapeHtml(name)}">📄 ${escapeHtml(name)} <span class="article-inline-file-caret">▾</span></a></p>`;
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

      const response = await api.post('/articles/upload-image', uploadData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const fileUrl = response.data?.files?.[0];

      if (!fileUrl || response.data?.error) {
        throw new Error(response.data?.msg || 'Failed to upload file.');
      }

      insertHtmlIntoContent(
        buildInlineFileHtml(fileUrl, file.name, isImageFile(file.name))
      );
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
      formData.append('existing_attachments', JSON.stringify(currentAttachments));

      attachments.forEach((file) => {
        formData.append('attachments', file);
      });

      await api.put(`/articles/${id}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      navigate('/admin/content');
    } catch (error) {
      console.error('Update article error:', error);
      setMessage(error.response?.data?.message || 'Failed to update article.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <section className="card-like">
        <p className="muted">Loading article...</p>
      </section>
    );
  }

  return (
    <div>
      <PageHeader
        title="Edit Article"
        subtitle="Update article details in the knowledge base."
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
              />
            </label>

            <label>
              Notion / Reference Link
              <input
                name="link"
                value={form.link}
                onChange={handleChange}
              />
            </label>

            <div className="full-width article-attachment-panel">
              <div className="article-attachment-top">
                <div>
                  <h3>Attach / Replace Image or File</h3>
                  <p>
                    Click add to select one or more images/files. You can click
                    the button again to add more before saving the article.
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

              {currentAttachments.length > 0 && (
                <div className="attachment-group">
                  <p className="attachment-group-title">Existing files</p>

                  <div className="attachment-list">
                    {currentAttachments.map((file, index) => {
                      const fileName = getAttachmentFileName(file);

                      return (
                        <div
                          className="attachment-card current"
                          key={`${fileName}-${index}`}
                        >
                          <span className="attachment-icon">
                            {isImageFile(fileName) ? 'IMG' : 'FILE'}
                          </span>

                          <div className="attachment-info">
                            <strong>{fileName}</strong>
                            <span>Existing article file</span>
                          </div>

                          <a
                            className="secondary-btn attachment-view-btn"
                            href={getFileUrl(file)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            View
                          </a>

                          <button
                            type="button"
                            className="secondary-btn attachment-view-btn"
                            onClick={() => insertExistingAttachmentIntoContent(index)}
                          >
                            Insert into Content
                          </button>

                          <button
                            type="button"
                            className="attachment-remove-btn"
                            onClick={() => removeCurrentAttachment(index)}
                          >
                            Remove
                          </button>
                        </div>
                      );
                    })}
                  </div>

                  <p className="attachment-hint">
                    Tip: use <strong>Insert into Content</strong> to move a file
                    into the article body at your cursor position, instead of
                    leaving it in this general Attachments list.
                  </p>
                </div>
              )}

              {attachments.length > 0 && (
                <div className="attachment-group">
                  <div className="attachment-group-header">
                    <p className="attachment-group-title">
                      New selected files ({attachments.length})
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
                </div>
              )}

              {attachments.length === 0 && currentAttachments.length === 0 && (
                <div className="empty-attachment-box">
                  No file selected yet. Click{' '}
                  <strong>+ Add Image / File</strong> to attach one or more
                  files.
                </div>
              )}
            </div>

            <label className="full-width">
              Article Content *

              <div className="article-rich-editor">
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
                  onChange={(newContent) =>
                    setForm((prev) => ({
                      ...prev,
                      content: newContent,
                    }))
                  }
                />
              </div>
            </label>
          </div>

          <div className="button-group">
            <button
              type="button"
              className="secondary-btn"
              onClick={() => navigate('/admin/content')}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="primary-btn narrow-btn"
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
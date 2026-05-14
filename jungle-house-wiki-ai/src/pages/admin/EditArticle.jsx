import { useEffect, useMemo, useRef, useState } from 'react';
import JoditEditor from 'jodit-react';
import { useNavigate, useParams } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];
const acceptedFileTypes =
  'image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp,image/svg+xml,.pdf,.doc,.docx';

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
  const [currentAttachment, setCurrentAttachment] = useState('');
  const [currentAttachments, setCurrentAttachments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

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
        insertImageAsBase64URI: true,
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

        setCurrentAttachment(article.attachment_url || '');

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

  const getAttachmentFileName = (file) => {
    const fileUrl = file?.url || file?.file_url || file?.path || file;
    return String(fileUrl || '').split('/').pop() || 'Attachment file';
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

              {currentAttachments.length > 0 && attachments.length === 0 && (
                <div className="attachment-group">
                  <p className="attachment-group-title">Current attachments</p>

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
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {currentAttachments.length === 0 &&
                currentAttachment &&
                attachments.length === 0 && (
                  <div className="attachment-group">
                    <p className="attachment-group-title">Current attachment</p>

                    <div className="attachment-list">
                      <div className="attachment-card current">
                        <span className="attachment-icon">
                          {isImageFile(currentAttachment) ? 'IMG' : 'FILE'}
                        </span>

                        <div className="attachment-info">
                          <strong>
                            {getAttachmentFileName(currentAttachment)}
                          </strong>
                          <span>Existing article file</span>
                        </div>
                      </div>
                    </div>
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

              {attachments.length === 0 &&
                currentAttachments.length === 0 &&
                !currentAttachment && (
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
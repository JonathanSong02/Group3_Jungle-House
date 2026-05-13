import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

const acceptedFileTypes =
  'image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp,image/svg+xml,.pdf,.doc,.docx';

export default function AddArticle() {
  const navigate = useNavigate();
  const contentTextareaRef = useRef(null);
  const fileInputRef = useRef(null);

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

  const createTableHtml = (rows, columns) => {
    let tableHtml = '\n\n<table class="article-data-table">\n  <tbody>\n';

    for (let row = 1; row <= rows; row += 1) {
      tableHtml += '    <tr>\n';

      for (let column = 1; column <= columns; column += 1) {
        tableHtml += `      <td>Cell ${row}-${column}</td>\n`;
      }

      tableHtml += '    </tr>\n';
    }

    tableHtml += '  </tbody>\n</table>\n\n';

    return tableHtml;
  };

  const insertTable = (rows, columns) => {
    const tableHtml = createTableHtml(rows, columns);
    const textarea = contentTextareaRef.current;

    setForm((prev) => {
      const currentContent = prev.content || '';

      if (!textarea) {
        return {
          ...prev,
          content: `${currentContent}${tableHtml}`,
        };
      }

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;

      const beforeCursor = currentContent.substring(0, start);
      const afterCursor = currentContent.substring(end);

      const updatedContent = `${beforeCursor}${tableHtml}${afterCursor}`;

      setTimeout(() => {
        textarea.focus();
        const cursorPosition = start + tableHtml.length;
        textarea.setSelectionRange(cursorPosition, cursorPosition);
      }, 0);

      return {
        ...prev,
        content: updatedContent,
      };
    });
  };

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

      await api.post('/articles', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

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

              {attachments.length === 0 && (
                <div className="empty-attachment-box">
                  No file selected yet. Click <strong>+ Add Image / File</strong>{' '}
                  to attach one or more files.
                </div>
              )}
            </div>

            <label className="full-width">
              Article Content *

              <div className="article-editor-toolbar">
                <span className="article-editor-toolbar-title">
                  Insert Table
                </span>

                <div className="table-size-picker">
                  {[1, 2, 3, 4, 5, 6].map((row) =>
                    [1, 2, 3, 4, 5, 6].map((column) => (
                      <button
                        key={`table-${row}-${column}`}
                        type="button"
                        className="table-size-cell"
                        title={`${row} x ${column} table`}
                        onClick={() => insertTable(row, column)}
                      >
                        {row === 1 ? column : ''}
                      </button>
                    ))
                  )}
                </div>

                <p className="muted small table-help-text">
                  Click a box to insert a table. After inserting, change the
                  cell text inside the article content.
                </p>
              </div>

              <textarea
                ref={contentTextareaRef}
                name="content"
                value={form.content}
                onChange={handleChange}
                rows="18"
                placeholder="Write article content here..."
              />
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
              {saving ? 'Creating...' : 'Create Article'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
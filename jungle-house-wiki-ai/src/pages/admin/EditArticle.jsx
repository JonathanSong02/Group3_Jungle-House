import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];
const acceptedFileTypes =
  'image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp,image/svg+xml,.pdf,.doc,.docx';

export default function EditArticle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const contentTextareaRef = useRef(null);

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

  const handleFileChange = (event) => {
    const files = Array.from(event.target.files || []);
    setAttachments(files);
  };

  const removeAttachment = (indexToRemove) => {
    setAttachments((prev) =>
      prev.filter((_, index) => index !== indexToRemove)
    );
  };

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

            <label className="full-width">
              Attach / Replace Image or File
              <input
                type="file"
                accept={acceptedFileTypes}
                multiple
                onChange={handleFileChange}
              />

              {currentAttachments.length > 0 && attachments.length === 0 && (
                <div className="muted top-gap-xs">
                  <p>Current attachments:</p>
                  <ul>
                    {currentAttachments.map((file, index) => {
                      const fileUrl = file.url || file;
                      const fileName = String(fileUrl).split('/').pop();

                      return <li key={`${fileName}-${index}`}>{fileName}</li>;
                    })}
                  </ul>
                </div>
              )}

              {currentAttachments.length === 0 &&
                currentAttachment &&
                attachments.length === 0 && (
                  <p className="muted top-gap-xs">
                    Current attachment: {currentAttachment.split('/').pop()}
                  </p>
                )}

              {attachments.length > 0 && (
                <div className="muted top-gap-xs">
                  <p>New selected files:</p>
                  <ul>
                    {attachments.map((file, index) => (
                      <li key={`${file.name}-${index}`}>
                        {file.name}{' '}
                        <button
                          type="button"
                          className="text-btn"
                          onClick={() => removeAttachment(index)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </label>

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
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
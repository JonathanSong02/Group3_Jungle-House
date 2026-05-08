import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

export default function AddArticle() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    title: '',
    category: 'SOP',
    sub_category: '',
    link: '',
    content: '',
  });

  const [attachment, setAttachment] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [preview, setPreview] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleFileChange = (event) => {
    const file = event.target.files[0];

    if (!file) {
      setAttachment(null);
      return;
    }

    setAttachment(file);
  };

  const clearForm = () => {
    setForm({
      title: '',
      category: 'SOP',
      sub_category: '',
      link: '',
      content: '',
    });

    setAttachment(null);
    setMessage('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.title.trim()) {
      setMessage('Please enter the article title.');
      return;
    }

    if (!form.content.trim()) {
      setMessage('Please enter the article content.');
      return;
    }

    try {
      setLoading(true);
      setMessage('');

      const formData = new FormData();
      formData.append('title', form.title.trim());
      formData.append('category', form.category.trim());
      formData.append('sub_category', form.sub_category.trim());
      formData.append('link', form.link.trim());
      formData.append('content', form.content.trim());

      if (attachment) {
        formData.append('attachment', attachment);
      }

      await api.post('/articles', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      navigate('/admin/content');
    } catch (error) {
      console.error('Add article error:', error);
      setMessage(error.response?.data?.message || 'Failed to save article.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Add Article"
        subtitle="Add new SOP, product, sales, notice, or training content into the knowledge base."
      />

      <section className="card-like top-gap-sm">
        <form onSubmit={handleSubmit} className="stack-gap">
          <div className="row-between wrap-gap">
            <div>
              <h3>Article Details</h3>
              <p className="muted">
                Fill in the article information. Title and content are required.
              </p>
            </div>

            <button
              type="button"
              className="secondary-btn"
              onClick={() => navigate('/admin/content')}
            >
              Back
            </button>
          </div>

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
                placeholder="Example: Opening SOP - Spring"
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
                placeholder="Example: Kiosk Opening"
              />
            </label>

            <label>
              Notion / Reference Link
              <input
                name="link"
                value={form.link}
                onChange={handleChange}
                placeholder="Paste reference link if needed"
              />
            </label>

            <label className="full-width">
              Attach Image / File
              <input
                type="file"
                accept="image/*,.pdf,.doc,.docx"
                onChange={handleFileChange}
              />
              {attachment && (
                <p className="muted top-gap-xs">
                  Selected file: {attachment.name}
                </p>
              )}
            </label>

            <label className="full-width">
              Article Content *
              <textarea
                name="content"
                value={form.content}
                onChange={handleChange}
                rows="18"
                placeholder="Write or paste article content here..."
              />
            </label>
          </div>

          <div className="button-group">
            <button
              type="button"
              className="secondary-btn"
              onClick={() => setPreview((prev) => !prev)}
            >
              {preview ? 'Hide Preview' : 'Preview'}
            </button>

            <button
              type="button"
              className="secondary-btn"
              onClick={clearForm}
            >
              Clear
            </button>

            <button
              type="submit"
              className="primary-btn narrow-btn"
              disabled={loading}
            >
              {loading ? 'Saving...' : 'Save Article'}
            </button>
          </div>
        </form>
      </section>

      {preview && (
        <section className="card-like top-gap-sm">
          <p className="eyebrow">{form.category}</p>
          <h3>{form.title || 'Article Title Preview'}</h3>

          {form.sub_category && (
            <p className="muted">Sub Category: {form.sub_category}</p>
          )}

          {attachment && (
            <p className="muted">Attachment: {attachment.name}</p>
          )}

          <div className="article-preview">
            <pre>{form.content || 'Article content preview will appear here.'}</pre>
          </div>
        </section>
      )}
    </div>
  );
}
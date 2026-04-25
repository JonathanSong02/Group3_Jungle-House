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

  const clearForm = () => {
    setForm({
      title: '',
      category: 'SOP',
      sub_category: '',
      link: '',
      content: '',
    });
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

      await api.post('/articles', {
        title: form.title.trim(),
        category: form.category.trim(),
        sub_category: form.sub_category.trim(),
        link: form.link.trim(),
        content: form.content.trim(),
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
                placeholder="Example: Opening SOP"
              />
            </label>

            <label>
              Notion / Reference Link
              <input
                name="link"
                value={form.link}
                onChange={handleChange}
                placeholder="Optional URL"
              />
            </label>

            <label className="full-width">
              Article Content *
              <textarea
                name="content"
                value={form.content}
                onChange={handleChange}
                placeholder={`Example:

Opening SOP - Spring

Steps
1. Clock in (TimeTec)
2. Take photo of the covered fabric of booth and send to group.
[IMAGE]
3. Open covered fabric, fold it and put inside the box.`}
                rows="18"
              />
            </label>
          </div>

          <div className="row-between wrap-gap">
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
                disabled={loading}
              >
                {loading ? 'Saving...' : 'Save Article'}
              </button>
            </div>
          </div>
        </form>
      </section>

      {preview && (
        <section className="card-like top-gap-sm">
          <p className="eyebrow">{form.category}</p>
          <h2>{form.title || 'Untitled Article'}</h2>
          <p className="muted">{form.sub_category || 'No sub category'}</p>

          {form.link && (
            <p>
              <a href={form.link} target="_blank" rel="noreferrer">
                Open reference link
              </a>
            </p>
          )}

          <pre className="article-preview">
            {form.content || 'No content yet.'}
          </pre>
        </section>
      )}
    </div>
  );
}
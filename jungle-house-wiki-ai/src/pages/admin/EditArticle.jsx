import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

export default function EditArticle() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    title: '',
    category: 'SOP',
    sub_category: '',
    link: '',
    content: '',
  });

  const [attachment, setAttachment] = useState(null);
  const [currentAttachment, setCurrentAttachment] = useState('');
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

  const handleFileChange = (event) => {
    const file = event.target.files[0];

    if (!file) {
      setAttachment(null);
      return;
    }

    setAttachment(file);
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

      if (attachment) {
        formData.append('attachment', attachment);
      }

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
                accept="image/*,.pdf,.doc,.docx"
                onChange={handleFileChange}
              />

              {currentAttachment && !attachment && (
                <p className="muted top-gap-xs">
                  Current attachment: {currentAttachment.split('/').pop()}
                </p>
              )}

              {attachment && (
                <p className="muted top-gap-xs">
                  New selected file: {attachment.name}
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
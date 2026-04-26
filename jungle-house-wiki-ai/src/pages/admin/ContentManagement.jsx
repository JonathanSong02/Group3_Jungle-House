import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

const categories = ['All', 'SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

export default function ContentManagement() {
  const navigate = useNavigate();

  const [articleList, setArticleList] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [loading, setLoading] = useState(true);

  const fetchArticles = async () => {
    try {
      setLoading(true);
      const response = await api.get('/articles');
      setArticleList(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch articles error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArticles();
  }, []);

  const filteredArticles = useMemo(() => {
    return articleList.filter((article) => {
      const categoryMatch =
        selectedCategory === 'All' || article.category === selectedCategory;

      const text = `${article.title || ''} ${article.category || ''} ${
        article.sub_category || ''
      }`.toLowerCase();

      return categoryMatch && text.includes(search.toLowerCase());
    });
  }, [articleList, search, selectedCategory]);

  const deleteArticle = async (articleId) => {
    const confirmDelete = window.confirm(
      'Are you sure you want to delete this article?'
    );

    if (!confirmDelete) return;

    try {
      await api.delete(`/articles/${articleId}`);

      setArticleList((prev) =>
        prev.filter((article) => article.article_id !== articleId)
      );
    } catch (error) {
      console.error('Delete article error:', error);
      alert(error.response?.data?.message || 'Failed to delete article.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Content Management"
        subtitle="Create, edit, delete, and organize knowledge content."
      />

      <section className="card-like top-gap-sm content-toolbar-card">
        <div className="content-toolbar-main">
          <div>
            <h3>Knowledge Articles</h3>
            <p className="muted">
              Manage SOP, product, sales, notice, and training content.
            </p>
          </div>

          <Link to="/admin/content/add" className="primary-btn narrow-btn link-btn">
            + Add Article
          </Link>
        </div>

        <div className="content-filter-row">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search article title, category, or sub category..."
          />

          <select
            value={selectedCategory}
            onChange={(event) => setSelectedCategory(event.target.value)}
          >
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </div>
      </section>

      <div className="content-info-bar">
        <p>
          Showing <strong>{filteredArticles.length}</strong> of{' '}
          <strong>{articleList.length}</strong> articles
        </p>

        <div className="content-category-chips">
          {categories.map((category) => (
            <button
              key={category}
              type="button"
              className={selectedCategory === category ? 'chip active' : 'chip'}
              onClick={() => setSelectedCategory(category)}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading articles...</p>
        </section>
      ) : filteredArticles.length === 0 ? (
        <section className="card-like top-gap-sm empty-state-card">
          <h3>No articles found</h3>
          <p className="muted">
            Try another keyword or add a new knowledge article.
          </p>
          <Link to="/admin/content/add" className="primary-btn narrow-btn link-btn">
            Add Article
          </Link>
        </section>
      ) : (
        <div className="content-card-grid top-gap-sm">
          {filteredArticles.map((article) => (
            <article
              key={article.article_id || article.id}
              className="card-like content-article-card"
            >
              <div>
                <div className="content-card-top">
                  <p className="eyebrow">{article.category || 'UNCATEGORIZED'}</p>
                  <span className="role-pill">
                    ID {article.article_id || article.id}
                  </span>
                </div>

                <h3>{article.title}</h3>

                <p className="muted">
                  {article.sub_category || 'No sub category'}
                </p>
              </div>

              <div className="button-group content-card-actions">
                <button
                  className="secondary-btn"
                  onClick={() =>
                    navigate(`/admin/content/edit/${article.article_id}`)
                  }
                >
                  Edit
                </button>

                <button
                  className="secondary-btn danger-btn"
                  onClick={() => deleteArticle(article.article_id)}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
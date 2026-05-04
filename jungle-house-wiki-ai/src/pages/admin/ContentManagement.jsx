import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const categories = ['All', 'SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

export default function ContentManagement() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const currentUserId = user?.user_id || user?.id || null;

  const [articleList, setArticleList] = useState([]);
  const [deletedArticleList, setDeletedArticleList] = useState([]);

  const [activeTab, setActiveTab] = useState('active');
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');

  const [selectedDeletedIds, setSelectedDeletedIds] = useState([]);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  const fetchArticles = async () => {
    try {
      setLoading(true);
      setMessage('');

      const [activeResponse, deletedResponse] = await Promise.all([
        api.get('/articles'),
        api.get('/articles?deleted=true'),
      ]);

      setArticleList(Array.isArray(activeResponse.data) ? activeResponse.data : []);
      setDeletedArticleList(
        Array.isArray(deletedResponse.data) ? deletedResponse.data : []
      );
    } catch (error) {
      console.error('Fetch articles error:', error);
      setMessage(error.response?.data?.message || 'Failed to load articles.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArticles();
  }, []);

  const currentList = activeTab === 'active' ? articleList : deletedArticleList;

  const filteredArticles = useMemo(() => {
    return currentList.filter((article) => {
      const categoryMatch =
        selectedCategory === 'All' || article.category === selectedCategory;

      const text = `${article.title || ''} ${article.category || ''} ${
        article.sub_category || ''
      }`.toLowerCase();

      return categoryMatch && text.includes(search.toLowerCase());
    });
  }, [currentList, search, selectedCategory]);

  const deleteArticle = async (articleId) => {
    const confirmDelete = window.confirm(
      'Move this article to Retrieve Bin? You can restore it later.'
    );

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/articles/${articleId}`, {
        data: {
          deleted_by: currentUserId,
        },
      });

      setMessage('Article moved to Retrieve Bin successfully.');
      await fetchArticles();
    } catch (error) {
      console.error('Delete article error:', error);
      alert(error.response?.data?.message || 'Failed to move article to bin.');
    }
  };

  const restoreArticle = async (articleId) => {
    const confirmRestore = window.confirm(
      'Restore this article back to active content?'
    );

    if (!confirmRestore) return;

    try {
      setMessage('');

      await api.put(`/articles/${articleId}/restore`);

      setMessage('Article restored successfully.');
      setSelectedDeletedIds((prev) => prev.filter((id) => id !== articleId));
      await fetchArticles();
    } catch (error) {
      console.error('Restore article error:', error);
      alert(error.response?.data?.message || 'Failed to restore article.');
    }
  };

  const toggleDeletedSelection = (articleId) => {
    setSelectedDeletedIds((prev) => {
      if (prev.includes(articleId)) {
        return prev.filter((id) => id !== articleId);
      }

      return [...prev, articleId];
    });
  };

  const toggleSelectAllDeleted = () => {
    const allVisibleDeletedIds = filteredArticles.map(
      (article) => article.article_id
    );

    const allSelected =
      allVisibleDeletedIds.length > 0 &&
      allVisibleDeletedIds.every((id) => selectedDeletedIds.includes(id));

    if (allSelected) {
      setSelectedDeletedIds((prev) =>
        prev.filter((id) => !allVisibleDeletedIds.includes(id))
      );
      return;
    }

    setSelectedDeletedIds((prev) => {
      const updatedIds = [...prev];

      allVisibleDeletedIds.forEach((id) => {
        if (!updatedIds.includes(id)) {
          updatedIds.push(id);
        }
      });

      return updatedIds;
    });
  };

  const permanentDeleteArticle = async (articleId) => {
    const confirmDelete = window.confirm(
      'Permanently delete this article? This action cannot be undone.'
    );

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/articles/${articleId}/permanent-delete`);

      setMessage('Article permanently deleted successfully.');
      setSelectedDeletedIds((prev) => prev.filter((id) => id !== articleId));
      await fetchArticles();
    } catch (error) {
      console.error('Permanent delete article error:', error);
      alert(error.response?.data?.message || 'Failed to permanently delete article.');
    }
  };

  const permanentDeleteSelected = async () => {
    const selectedVisibleIds = selectedDeletedIds.filter((id) =>
      filteredArticles.some((article) => article.article_id === id)
    );

    if (selectedVisibleIds.length === 0) {
      setMessage('Please select at least one article to delete permanently.');
      return;
    }

    const confirmDelete = window.confirm(
      `Permanently delete ${selectedVisibleIds.length} selected article(s)? This action cannot be undone.`
    );

    if (!confirmDelete) return;

    try {
      setBulkDeleting(true);
      setMessage('');

      await Promise.all(
        selectedVisibleIds.map((articleId) =>
          api.delete(`/articles/${articleId}/permanent-delete`)
        )
      );

      setMessage(`${selectedVisibleIds.length} article(s) permanently deleted.`);
      setSelectedDeletedIds([]);
      await fetchArticles();
    } catch (error) {
      console.error('Bulk permanent delete error:', error);
      alert(error.response?.data?.message || 'Failed to delete selected articles.');
    } finally {
      setBulkDeleting(false);
    }
  };

  const switchTab = (tabName) => {
    setActiveTab(tabName);
    setSearch('');
    setSelectedCategory('All');
    setSelectedDeletedIds([]);
    setMessage('');
  };

  const selectedVisibleDeletedIds = selectedDeletedIds.filter((id) =>
    filteredArticles.some((article) => article.article_id === id)
  );

  const allVisibleDeletedSelected =
    filteredArticles.length > 0 &&
    filteredArticles.every((article) =>
      selectedDeletedIds.includes(article.article_id)
    );

  return (
    <div>
      <PageHeader
        title="Content Management"
        subtitle="Create, edit, delete, retrieve, and organize knowledge content."
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

        <div className="content-management-tabs">
          <button
            type="button"
            className={activeTab === 'active' ? 'primary-btn' : 'secondary-btn'}
            onClick={() => switchTab('active')}
          >
            Active Articles ({articleList.length})
          </button>

          <button
            type="button"
            className={activeTab === 'bin' ? 'primary-btn' : 'secondary-btn'}
            onClick={() => switchTab('bin')}
          >
            Retrieve Bin ({deletedArticleList.length})
          </button>
        </div>

        <div className="content-filter-row">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={
              activeTab === 'active'
                ? 'Search active article title, category, or sub category...'
                : 'Search deleted article title, category, or sub category...'
            }
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

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      <div className="content-info-bar">
        <p>
          Showing <strong>{filteredArticles.length}</strong> of{' '}
          <strong>{currentList.length}</strong>{' '}
          {activeTab === 'active' ? 'active articles' : 'deleted articles'}
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

      {activeTab === 'bin' && (
        <section className="card-like top-gap-sm retrieve-bin-notice">
          <div className="row-between wrap-gap">
            <div>
              <p className="eyebrow">Retrieve Bin</p>
              <h3>Temporary deleted articles</h3>
              <p className="muted">
                Deleted articles are stored here so admin can restore them if content
                was removed by mistake.
              </p>
            </div>

            {filteredArticles.length > 0 && (
              <div className="button-group wrap-gap">
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={toggleSelectAllDeleted}
                >
                  {allVisibleDeletedSelected ? 'Clear All' : 'Select All'}
                </button>

                <button
                  type="button"
                  className="danger-btn"
                  onClick={permanentDeleteSelected}
                  disabled={selectedVisibleDeletedIds.length === 0 || bulkDeleting}
                >
                  {bulkDeleting
                    ? 'Deleting...'
                    : `Delete Selected (${selectedVisibleDeletedIds.length})`}
                </button>
              </div>
            )}
          </div>
        </section>
      )}

      {loading ? (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading articles...</p>
        </section>
      ) : filteredArticles.length === 0 ? (
        <section className="card-like top-gap-sm empty-state-card">
          <h3>
            {activeTab === 'active'
              ? 'No active articles found'
              : 'Retrieve Bin is empty'}
          </h3>

          <p className="muted">
            {activeTab === 'active'
              ? 'Try another keyword or add a new knowledge article.'
              : 'Deleted articles will appear here when admin removes content.'}
          </p>

          {activeTab === 'active' && (
            <Link to="/admin/content/add" className="primary-btn narrow-btn link-btn">
              Add Article
            </Link>
          )}
        </section>
      ) : (
        <div className="content-card-grid top-gap-sm">
          {filteredArticles.map((article) => (
            <article
              key={article.article_id || article.id}
              className={
                activeTab === 'bin'
                  ? selectedDeletedIds.includes(article.article_id)
                    ? 'card-like content-article-card deleted-article-card selected'
                    : 'card-like content-article-card deleted-article-card'
                  : 'card-like content-article-card'
              }
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

                {activeTab === 'bin' && (
                  <p className="muted small top-gap-sm">
                    Deleted at: {article.deleted_at || 'Not recorded'}
                  </p>
                )}
              </div>

              <div className="button-group content-card-actions">
                {activeTab === 'active' ? (
                  <>
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={() =>
                        navigate(`/admin/content/edit/${article.article_id}`)
                      }
                    >
                      Edit
                    </button>

                    <button
                      type="button"
                      className="secondary-btn danger-btn"
                      onClick={() => deleteArticle(article.article_id)}
                    >
                      Move to Bin
                    </button>
                  </>
                ) : (
                  <div className="retrieve-bin-actions">
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={selectedDeletedIds.includes(article.article_id)}
                        onChange={() => toggleDeletedSelection(article.article_id)}
                      />
                      <span>Select</span>
                    </label>

                    <div className="button-group wrap-gap">
                      <button
                        type="button"
                        className="primary-btn"
                        onClick={() => restoreArticle(article.article_id)}
                      >
                        Restore
                      </button>

                      <button
                        type="button"
                        className="danger-btn"
                        onClick={() => permanentDeleteArticle(article.article_id)}
                      >
                        Delete Permanently
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
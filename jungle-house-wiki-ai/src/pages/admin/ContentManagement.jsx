import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const CATEGORIES = ['All', 'SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

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
      setDeletedArticleList(Array.isArray(deletedResponse.data) ? deletedResponse.data : []);
    } catch (error) {
      console.error('Fetch articles error:', error);
      setMessage(error.response?.data?.message || 'Unable to load articles.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArticles();
  }, []);

  const currentList = activeTab === 'active' ? articleList : deletedArticleList;

  const filteredArticles = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return currentList.filter((article) => {
      const categoryMatch =
        selectedCategory === 'All' || article.category === selectedCategory;

      const text = `${article.title || ''} ${article.category || ''} ${
        article.sub_category || ''
      }`.toLowerCase();

      return categoryMatch && (!keyword || text.includes(keyword));
    });
  }, [currentList, search, selectedCategory]);

  const categoryCounts = useMemo(() => {
    const counts = { All: currentList.length };
    CATEGORIES.slice(1).forEach((category) => {
      counts[category] = currentList.filter(
        (article) => article.category === category
      ).length;
    });
    return counts;
  }, [currentList]);

  const deleteArticle = async (articleId) => {
    if (!window.confirm('Move this article to Retrieve Bin?')) return;

    try {
      setMessage('');
      await api.delete(`/articles/${articleId}`, {
        data: { deleted_by: currentUserId },
      });
      setMessage('Article moved to Retrieve Bin.');
      await fetchArticles();
    } catch (error) {
      console.error('Delete article error:', error);
      setMessage(error.response?.data?.message || 'Unable to move article.');
    }
  };

  const restoreArticle = async (articleId) => {
    if (!window.confirm('Restore this article?')) return;

    try {
      setMessage('');
      await api.put(`/articles/${articleId}/restore`);
      setMessage('Article restored.');
      setSelectedDeletedIds((prev) => prev.filter((id) => id !== articleId));
      await fetchArticles();
    } catch (error) {
      console.error('Restore article error:', error);
      setMessage(error.response?.data?.message || 'Unable to restore article.');
    }
  };

  const toggleDeletedSelection = (articleId) => {
    setSelectedDeletedIds((prev) =>
      prev.includes(articleId)
        ? prev.filter((id) => id !== articleId)
        : [...prev, articleId]
    );
  };

  const toggleSelectAllDeleted = () => {
    const visibleIds = filteredArticles.map((article) => article.article_id);
    const allSelected =
      visibleIds.length > 0 &&
      visibleIds.every((id) => selectedDeletedIds.includes(id));

    if (allSelected) {
      setSelectedDeletedIds((prev) =>
        prev.filter((id) => !visibleIds.includes(id))
      );
      return;
    }

    setSelectedDeletedIds((prev) => [...new Set([...prev, ...visibleIds])]);
  };

  const permanentDeleteArticle = async (articleId) => {
    if (!window.confirm('Permanently delete this article?')) return;

    try {
      setMessage('');
      await api.delete(`/articles/${articleId}/permanent-delete`);
      setMessage('Article permanently deleted.');
      setSelectedDeletedIds((prev) => prev.filter((id) => id !== articleId));
      await fetchArticles();
    } catch (error) {
      console.error('Permanent delete article error:', error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          'Unable to delete article.'
      );
    }
  };

  const permanentDeleteSelected = async () => {
    const selectedVisibleIds = selectedDeletedIds.filter((id) =>
      filteredArticles.some((article) => article.article_id === id)
    );

    if (selectedVisibleIds.length === 0) return;

    if (
      !window.confirm(
        `Permanently delete ${selectedVisibleIds.length} selected article(s)?`
      )
    ) {
      return;
    }

    try {
      setBulkDeleting(true);
      setMessage('');

      const response = await api.post('/articles/bulk-permanent-delete', {
        article_ids: selectedVisibleIds,
        deleted_by: currentUserId,
      });

      setMessage(
        response.data?.message ||
          `${selectedVisibleIds.length} article(s) deleted.`
      );

      setSelectedDeletedIds([]);
      await fetchArticles();
    } catch (error) {
      console.error('Bulk permanent delete error:', error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          'Unable to delete selected articles.'
      );
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

  const categoryTotal = new Set(
    articleList.map((article) => article.category).filter(Boolean)
  ).size;

  return (
    <div className="cm-page">
      <div className="cm-page-heading">
        <PageHeader
          title="Content Management"
          subtitle="Manage knowledge articles."
        />

        <Link to="/admin/content/add" className="cm-add-btn">
          <span aria-hidden="true">+</span>
          Add Article
        </Link>
      </div>

      <section className="cm-summary-grid" aria-label="Content overview">
        <button
          type="button"
          className={`cm-summary-card ${activeTab === 'active' ? 'active' : ''}`}
          onClick={() => switchTab('active')}
        >
          <span>Active Articles</span>
          <strong>{articleList.length}</strong>
        </button>

        <button
          type="button"
          className={`cm-summary-card ${activeTab === 'bin' ? 'active' : ''}`}
          onClick={() => switchTab('bin')}
        >
          <span>Retrieve Bin</span>
          <strong>{deletedArticleList.length}</strong>
        </button>

        <div className="cm-summary-card static">
          <span>Categories</span>
          <strong>{categoryTotal}</strong>
        </div>
      </section>

      <section className="cm-workspace">
        <div className="cm-workspace-head">
          <div className="cm-tabs">
            <button
              type="button"
              className={activeTab === 'active' ? 'active' : ''}
              onClick={() => switchTab('active')}
            >
              Articles
              <span>{articleList.length}</span>
            </button>

            <button
              type="button"
              className={activeTab === 'bin' ? 'active' : ''}
              onClick={() => switchTab('bin')}
            >
              Retrieve Bin
              <span>{deletedArticleList.length}</span>
            </button>
          </div>

          <div className="cm-search-tools">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search articles"
              aria-label="Search articles"
            />

            <select
              value={selectedCategory}
              onChange={(event) => setSelectedCategory(event.target.value)}
              aria-label="Filter by category"
            >
              {CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="cm-category-bar">
          {CATEGORIES.map((category) => (
            <button
              key={category}
              type="button"
              className={selectedCategory === category ? 'active' : ''}
              onClick={() => setSelectedCategory(category)}
            >
              {category}
              <span>{categoryCounts[category] || 0}</span>
            </button>
          ))}
        </div>

        {message ? <div className="cm-feedback">{message}</div> : null}

        {activeTab === 'bin' && filteredArticles.length > 0 ? (
          <div className="cm-bin-toolbar">
            <label className="cm-select-all">
              <input
                type="checkbox"
                checked={allVisibleDeletedSelected}
                onChange={toggleSelectAllDeleted}
              />
              <span>Select all</span>
            </label>

            <span className="cm-selection-count">
              {selectedVisibleDeletedIds.length} selected
            </span>

            <button
              type="button"
              className="cm-btn danger"
              onClick={permanentDeleteSelected}
              disabled={
                selectedVisibleDeletedIds.length === 0 || bulkDeleting
              }
            >
              {bulkDeleting ? 'Deleting...' : 'Delete Selected'}
            </button>
          </div>
        ) : null}

        {loading ? (
          <div className="cm-empty-state">
            <span className="cm-loading-dot" />
            <strong>Loading articles...</strong>
          </div>
        ) : filteredArticles.length === 0 ? (
          <div className="cm-empty-state">
            <strong>
              {activeTab === 'active'
                ? 'No articles found'
                : 'Retrieve Bin is empty'}
            </strong>

            {activeTab === 'active' ? (
              <Link to="/admin/content/add" className="cm-btn primary">
                Add Article
              </Link>
            ) : null}
          </div>
        ) : (
          <div className="cm-table-wrap">
            <table className="cm-table">
              <thead>
                <tr>
                  {activeTab === 'bin' ? <th className="cm-check-col" /> : null}
                  <th>Article</th>
                  <th>Category</th>
                  <th>ID</th>
                  {activeTab === 'bin' ? <th>Deleted</th> : null}
                  <th className="cm-action-col">Action</th>
                </tr>
              </thead>

              <tbody>
                {filteredArticles.map((article) => {
                  const articleId = article.article_id || article.id;
                  const selected = selectedDeletedIds.includes(
                    article.article_id
                  );

                  return (
                    <tr
                      key={articleId}
                      className={selected ? 'selected' : ''}
                    >
                      {activeTab === 'bin' ? (
                        <td className="cm-check-col">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() =>
                              toggleDeletedSelection(article.article_id)
                            }
                            aria-label={`Select ${article.title}`}
                          />
                        </td>
                      ) : null}

                      <td>
                        <div className="cm-article-cell">
                          <strong>{article.title}</strong>
                          <span>
                            {article.sub_category || 'No sub category'}
                          </span>
                        </div>
                      </td>

                      <td>
                        <span className="cm-category-badge">
                          {article.category || 'Uncategorized'}
                        </span>
                      </td>

                      <td>
                        <span className="cm-id">#{articleId}</span>
                      </td>

                      {activeTab === 'bin' ? (
                        <td>
                          <span className="cm-date">
                            {article.deleted_at || 'Not recorded'}
                          </span>
                        </td>
                      ) : null}

                      <td>
                        <div className="cm-actions">
                          {activeTab === 'active' ? (
                            <>
                              <button
                                type="button"
                                className="cm-btn secondary"
                                onClick={() =>
                                  navigate(`/admin/content/edit/${article.article_id}`)
                                }
                              >
                                Edit
                              </button>

                              <button
                                type="button"
                                className="cm-btn danger-soft"
                                onClick={() =>
                                  deleteArticle(article.article_id)
                                }
                              >
                                Move to Bin
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="cm-btn primary"
                                onClick={() =>
                                  restoreArticle(article.article_id)
                                }
                              >
                                Restore
                              </button>

                              <button
                                type="button"
                                className="cm-btn danger"
                                onClick={() =>
                                  permanentDeleteArticle(article.article_id)
                                }
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

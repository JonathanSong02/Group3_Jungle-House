import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';

const CATEGORIES = ['All', 'SOP', 'PRODUCT', 'SALES', 'Training', 'Notice', 'Notion'];

export default function ContentManagement() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t, tOr } = useLanguage();
  const catLabel = (category) => tOr(`cat.${category}`, category);
  const currentUserId = user?.user_id || user?.id || null;

  const [articleList, setArticleList] = useState([]);
  const [deletedArticleList, setDeletedArticleList] = useState([]);
  const [activeTab, setActiveTab] = useState('active');
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  // One selection list shared by both tabs -- safe because switchTab()
  // already clears it on every tab change, so an ID from the Articles tab
  // can never linger while viewing the Retrieve Bin or vice versa.
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkProcessing, setBulkProcessing] = useState(false);
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
      setMessage(error.response?.data?.message || t('cm.err.load'));
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
    if (!window.confirm(t('cm.confirm.bin'))) return;

    try {
      setMessage('');
      await api.delete(`/articles/${articleId}`, {
        data: { deleted_by: currentUserId },
      });
      setMessage(t('cm.ok.bin'));
      await fetchArticles();
    } catch (error) {
      console.error('Delete article error:', error);
      setMessage(error.response?.data?.message || t('cm.err.bin'));
    }
  };

  const restoreArticle = async (articleId) => {
    if (!window.confirm(t('cm.confirm.restore'))) return;

    try {
      setMessage('');
      await api.put(`/articles/${articleId}/restore`);
      setMessage(t('cm.ok.restore'));
      setSelectedIds((prev) => prev.filter((id) => id !== articleId));
      await fetchArticles();
    } catch (error) {
      console.error('Restore article error:', error);
      setMessage(error.response?.data?.message || t('cm.err.restore'));
    }
  };

  const toggleSelection = (articleId) => {
    setSelectedIds((prev) =>
      prev.includes(articleId)
        ? prev.filter((id) => id !== articleId)
        : [...prev, articleId]
    );
  };

  const toggleSelectAllVisible = () => {
    const visibleIds = filteredArticles.map((article) => article.article_id);
    const allSelected =
      visibleIds.length > 0 &&
      visibleIds.every((id) => selectedIds.includes(id));

    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !visibleIds.includes(id)));
      return;
    }

    setSelectedIds((prev) => [...new Set([...prev, ...visibleIds])]);
  };

  const clearSelection = () => setSelectedIds([]);

  const permanentDeleteArticle = async (articleId) => {
    if (!window.confirm(t('cm.confirm.perm'))) return;

    try {
      setMessage('');
      await api.delete(`/articles/${articleId}/permanent-delete`);
      setMessage(t('cm.ok.perm'));
      setSelectedIds((prev) => prev.filter((id) => id !== articleId));
      await fetchArticles();
    } catch (error) {
      console.error('Permanent delete article error:', error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('cm.err.perm')
      );
    }
  };

  // Shared by all three bulk actions below -- same validation, same
  // confirm-before-acting safety net, same success/error handling shape,
  // just a different endpoint and confirm/result wording per action.
  const runBulkAction = async ({ endpoint, confirmText, successFallback, errorFallback }) => {
    const selectedVisibleIds = selectedIds.filter((id) =>
      filteredArticles.some((article) => article.article_id === id)
    );

    if (selectedVisibleIds.length === 0) return;

    if (confirmText && !window.confirm(confirmText(selectedVisibleIds.length))) {
      return;
    }

    try {
      setBulkProcessing(true);
      setMessage('');

      await api.post(endpoint, {
        article_ids: selectedVisibleIds,
        actor_id: currentUserId,
      });

      setMessage(successFallback(selectedVisibleIds.length));

      setSelectedIds([]);
      await fetchArticles();
    } catch (error) {
      console.error(`Bulk action error (${endpoint}):`, error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          errorFallback
      );
    } finally {
      setBulkProcessing(false);
    }
  };

  const bulkMoveToBin = () =>
    runBulkAction({
      endpoint: '/articles/bulk-bin',
      confirmText: (count) => t('cm.bulk.confirmBin', { n: count }),
      successFallback: (count) => t('cm.bulk.okBin', { n: count }),
      errorFallback: t('cm.bulk.errBin'),
    });

  const bulkRestoreSelected = () =>
    runBulkAction({
      endpoint: '/articles/bulk-restore',
      confirmText: null,
      successFallback: (count) => t('cm.bulk.okRestore', { n: count }),
      errorFallback: t('cm.bulk.errRestore'),
    });

  const permanentDeleteSelected = () =>
    runBulkAction({
      endpoint: '/articles/bulk-permanent-delete',
      confirmText: (count) => t('cm.bulk.confirmPerm', { n: count }),
      successFallback: (count) => t('cm.bulk.okPerm', { n: count }),
      errorFallback: t('cm.bulk.errPerm'),
    });

  const switchTab = (tabName) => {
    setActiveTab(tabName);
    setSearch('');
    setSelectedCategory('All');
    setSelectedIds([]);
    setMessage('');
  };

  const selectedVisibleIds = selectedIds.filter((id) =>
    filteredArticles.some((article) => article.article_id === id)
  );

  const allVisibleSelected =
    filteredArticles.length > 0 &&
    filteredArticles.every((article) => selectedIds.includes(article.article_id));

  const categoryTotal = new Set(
    articleList.map((article) => article.category).filter(Boolean)
  ).size;

  return (
    <div className="cm-page">
      <div className="cm-page-heading">
        <PageHeader
          title={t('nav.contentManagement')}
          subtitle={t('cm.subtitle')}
        />

        <Link to="/admin/content/add" className="cm-add-btn">
          <span aria-hidden="true">+</span>
          {t('kb.newArticle')}
        </Link>
      </div>

      <section className="cm-summary-grid" aria-label={t('cm.overviewAria')}>
        <button
          type="button"
          className={`cm-summary-card ${activeTab === 'active' ? 'active' : ''}`}
          onClick={() => switchTab('active')}
        >
          <span>{t('cm.activeArticles')}</span>
          <strong>{articleList.length}</strong>
        </button>

        <button
          type="button"
          className={`cm-summary-card ${activeTab === 'bin' ? 'active' : ''}`}
          onClick={() => switchTab('bin')}
        >
          <span>{t('cm.retrieveBin')}</span>
          <strong>{deletedArticleList.length}</strong>
        </button>

        <div className="cm-summary-card static">
          <span>{t('cm.categories')}</span>
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
              {t('cm.articles')}
              <span>{articleList.length}</span>
            </button>

            <button
              type="button"
              className={activeTab === 'bin' ? 'active' : ''}
              onClick={() => switchTab('bin')}
            >
              {t('cm.retrieveBin')}
              <span>{deletedArticleList.length}</span>
            </button>
          </div>

          <div className="cm-search-tools">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('kb.searchPlaceholder')}
              aria-label={t('kb.searchArticles')}
            />

            <select
              value={selectedCategory}
              onChange={(event) => setSelectedCategory(event.target.value)}
              aria-label={t('cm.filterCategory')}
            >
              {CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {catLabel(category)}
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
              {catLabel(category)}
              <span>{categoryCounts[category] || 0}</span>
            </button>
          ))}
        </div>

        {message ? <div className="cm-feedback">{message}</div> : null}

        {filteredArticles.length > 0 && selectedVisibleIds.length > 0 ? (
          <div className="cm-bin-toolbar" role="toolbar" aria-label={t('cm.bulkAria')}>
            <span className="cm-selection-count">
              {t('cm.nSelected', { n: selectedVisibleIds.length })}
            </span>

            <button
              type="button"
              className="cm-btn secondary"
              onClick={clearSelection}
              disabled={bulkProcessing}
            >
              {t('cm.clearSelection')}
            </button>

            {activeTab === 'active' ? (
              <button
                type="button"
                className="cm-btn danger-soft"
                onClick={bulkMoveToBin}
                disabled={bulkProcessing}
              >
                {bulkProcessing ? t('cm.moving') : t('cm.moveSelected')}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="cm-btn primary"
                  onClick={bulkRestoreSelected}
                  disabled={bulkProcessing}
                >
                  {bulkProcessing ? t('cm.restoring') : t('cm.restoreSelected')}
                </button>

                <button
                  type="button"
                  className="cm-btn danger"
                  onClick={permanentDeleteSelected}
                  disabled={bulkProcessing}
                >
                  {bulkProcessing ? t('cm.deleting') : t('cm.deleteSelected')}
                </button>
              </>
            )}
          </div>
        ) : null}

        {loading ? (
          <div className="cm-empty-state">
            <span className="cm-loading-dot" />
            <strong>{t('cm.loading')}</strong>
          </div>
        ) : filteredArticles.length === 0 ? (
          <div className="cm-empty-state">
            <strong>
              {activeTab === 'active'
                ? t('cm.noArticles')
                : t('cm.binEmpty')}
            </strong>

            {activeTab === 'active' ? (
              <Link to="/admin/content/add" className="cm-btn primary">
                {t('kb.newArticle')}
              </Link>
            ) : null}
          </div>
        ) : (
          <div className="cm-table-wrap">
            <table className="cm-table">
              <thead>
                <tr>
                  <th className="cm-check-col">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      aria-label={t('cm.selectAll')}
                    />
                  </th>
                  <th>{t('cm.col.article')}</th>
                  <th>{t('cm.col.category')}</th>
                  <th>ID</th>
                  {activeTab === 'bin' ? <th>{t('cm.col.deleted')}</th> : null}
                  <th className="cm-action-col">{t('cm.col.action')}</th>
                </tr>
              </thead>

              <tbody>
                {filteredArticles.map((article) => {
                  const articleId = article.article_id || article.id;
                  const selected = selectedIds.includes(article.article_id);

                  return (
                    <tr
                      key={articleId}
                      className={selected ? 'selected' : ''}
                    >
                      <td className="cm-check-col">
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleSelection(article.article_id)}
                          aria-label={t('cm.select', { title: article.title })}
                        />
                      </td>

                      <td>
                        <div className="cm-article-cell">
                          <strong>{article.title}</strong>
                          <span>
                            {article.sub_category || t('cm.noSubCategory')}
                          </span>
                        </div>
                      </td>

                      <td>
                        <span className="cm-category-badge">
                          {catLabel(article.category || 'Uncategorized')}
                        </span>
                      </td>

                      <td>
                        <span className="cm-id">#{articleId}</span>
                      </td>

                      {activeTab === 'bin' ? (
                        <td>
                          <span className="cm-date">
                            {article.deleted_at || t('cm.notRecorded')}
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
                                {t('common.edit')}
                              </button>

                              <button
                                type="button"
                                className="cm-btn danger-soft"
                                onClick={() =>
                                  deleteArticle(article.article_id)
                                }
                              >
                                {t('cm.moveToBin')}
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
                                {t('cm.restore')}
                              </button>

                              <button
                                type="button"
                                className="cm-btn danger"
                                onClick={() =>
                                  permanentDeleteArticle(article.article_id)
                                }
                              >
                                {t('common.delete')}
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

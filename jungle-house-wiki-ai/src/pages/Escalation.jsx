import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

function buildImageUrl(url) {
  if (!url) return '';

  if (url.startsWith('http')) {
    return url;
  }

  if (url.startsWith('/')) {
    return `${API_BASE_URL}${url}`;
  }

  return `${API_BASE_URL}/${url}`;
}

const API_BASE_URL = 'https://group3jungle-house-production.up.railway.app';

export default function Escalation() {
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [trashItems, setTrashItems] = useState([]);
  const [answers, setAnswers] = useState({});
  const [answerImages, setAnswerImages] = useState({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState('pending');

  // Delete mode states
  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const fetchEscalations = async () => {
    try {
      setLoading(true);

      const [activeResponse, trashResponse] = await Promise.all([
        api.get('/escalations'),
        api.get('/escalations?deleted=true'),
      ]);

      const activeData = Array.isArray(activeResponse.data) ? activeResponse.data : [];
      const trashData = Array.isArray(trashResponse.data) ? trashResponse.data : [];

      setItems(activeData);
      setTrashItems(trashData);

      const answerMap = {};
      activeData.forEach((item) => {
        answerMap[item.escalation_id] = item.manual_answer || '';
      });

      setAnswers(answerMap);
    } catch (error) {
      console.error('Fetch escalations error:', error);
      setMessage('Failed to load escalations.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEscalations();
  }, []);

  const pendingItems = useMemo(() => {
    return items.filter(
      (item) => item.status === 'pending' || item.status === 'reviewing'
    );
  }, [items]);

  const resolvedItems = useMemo(() => {
    return items.filter((item) => item.status === 'resolved');
  }, [items]);

  const filteredItems =
    activeTab === 'pending'
      ? pendingItems
      : activeTab === 'resolved'
        ? resolvedItems
        : trashItems;

  const filteredItemIds = useMemo(() => {
    return filteredItems.map((item) => item.escalation_id);
  }, [filteredItems]);

  const selectedVisibleIds = useMemo(() => {
    return selectedIds.filter((id) => filteredItemIds.includes(id));
  }, [selectedIds, filteredItemIds]);

  const isAllSelected =
    filteredItems.length > 0 && selectedVisibleIds.length === filteredItems.length;

  const updateAnswer = (id, value) => {
    setAnswers((prev) => ({
      ...prev,
      [id]: value,
    }));
  };

  const submitAnswer = async (id) => {
    const manualAnswer = answers[id];
    const selectedImage = answerImages[id];

    if (!manualAnswer || !manualAnswer.trim()) {
      setMessage('Please write a manual answer before submitting.');
      return;
    }

    try {
      setMessage('');

      const formData = new FormData();
      formData.append('manual_answer', manualAnswer.trim());
      formData.append('handled_by', user?.user_id || user?.id || '');

      if (selectedImage) {
        formData.append('image', selectedImage);
      }

      await api.put(`/escalations/${id}/answer`, formData);

      setMessage('Manual answer submitted successfully.');
      setActiveTab('resolved');
      setDeleteMode(false);
      setSelectedIds([]);

      setAnswerImages((prev) => {
        const updated = { ...prev };
        delete updated[id];
        return updated;
      });

      fetchEscalations();
        } catch (error) {
          console.error('Submit manual answer error:', error);

          const backendMessage =
            error?.response?.data?.error ||
            error?.response?.data?.message ||
            'Failed to submit manual answer.';

          setMessage(backendMessage);
        }
  };

  const startDeleteMode = () => {
    setDeleteMode(true);
    setSelectedIds([]);
    setMessage('');
  };

  const cancelDeleteMode = () => {
    setDeleteMode(false);
    setSelectedIds([]);
    setMessage('');
  };

  const toggleSelectOne = (id) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((selectedId) => selectedId !== id);
      }

      return [...prev, id];
    });
  };

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedIds((prev) =>
        prev.filter((id) => !filteredItemIds.includes(id))
      );
      return;
    }

    setSelectedIds((prev) => {
      const updatedIds = [...prev];

      filteredItemIds.forEach((id) => {
        if (!updatedIds.includes(id)) {
          updatedIds.push(id);
        }
      });

      return updatedIds;
    });
  };

  const openBulkDeleteModal = () => {
    if (selectedVisibleIds.length === 0) {
      setMessage('Please select at least one escalation to delete.');
      return;
    }

    setBulkDeleteOpen(true);
  };

  const closeBulkDeleteModal = () => {
    if (bulkDeleting) return;
    setBulkDeleteOpen(false);
  };

  const confirmBulkDelete = async () => {
    if (selectedVisibleIds.length === 0) return;

    try {
      setMessage('');
      setBulkDeleting(true);

      await Promise.all(
        selectedVisibleIds.map((id) =>
          api.delete(`/escalations/${id}`, {
            data: {
              deleted_by: user?.user_id || user?.id || null,
            },
          })
        )
      );

      setItems((prev) =>
        prev.filter((item) => !selectedVisibleIds.includes(item.escalation_id))
      );

      setAnswers((prev) => {
        const updatedAnswers = { ...prev };

        selectedVisibleIds.forEach((id) => {
          delete updatedAnswers[id];
        });

        return updatedAnswers;
      });

      setMessage(`${selectedVisibleIds.length} escalation(s) moved to Trash Bin successfully.`);
      setSelectedIds([]);
      setBulkDeleteOpen(false);
      setDeleteMode(false);

      fetchEscalations();
    } catch (error) {
      console.error('Bulk delete escalation error:', error);

      setMessage(
        error.response?.data?.message ||
        error.response?.data?.error ||
        'Failed to delete selected escalations.'
      );
    } finally {
      setBulkDeleting(false);
    }
  };

  const restoreEscalation = async (id) => {
    try {
      setMessage('');

      await api.put(`/escalations/${id}/restore`);

      setMessage('Escalation restored successfully.');
      fetchEscalations();
    } catch (error) {
      console.error('Restore escalation error:', error);

      setMessage(
        error.response?.data?.message ||
        error.response?.data?.error ||
        'Failed to restore escalation.'
      );
    }
  };

  const permanentDeleteEscalation = async (id) => {
    try {
      setMessage('');

      await api.delete(`/escalations/${id}/permanent-delete`);

      setMessage('Escalation permanently deleted successfully.');
      fetchEscalations();
    } catch (error) {
      console.error('Permanent delete escalation error:', error);

      setMessage(
        error.response?.data?.message ||
        error.response?.data?.error ||
        'Failed to permanently delete escalation.'
      );
    }
  };

  return (
    <div>
      <PageHeader
        title="Escalation"
        subtitle="Handle weak AI answers through manual follow-up and review status tracking."
      />

      <section className="card-like top-gap-sm">
        <div className="row-between wrap-gap">
          <div>
            <h3>Escalation Review</h3>
            <p className="muted">
              Pending questions need manual answers. Resolved questions have already been answered.
            </p>
          </div>

          <div className="row-gap escalation-top-actions">
            <button
              type="button"
              className={activeTab === 'pending' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => {
                setActiveTab('pending');
                setDeleteMode(false);
                setSelectedIds([]);
              }}
            >
              Pending ({pendingItems.length})
            </button>

            <button
              type="button"
              className={activeTab === 'resolved' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => {
                setActiveTab('resolved');
                setDeleteMode(false);
                setSelectedIds([]);
              }}
            >
              Resolved ({resolvedItems.length})
            </button>

            <button
              type="button"
              className={activeTab === 'trash' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => {
                setActiveTab('trash');
                setDeleteMode(false);
                setSelectedIds([]);
              }}
            >
              Trash Bin ({trashItems.length})
            </button>

            {!deleteMode ? (
              <button
                type="button"
                className="danger-btn"
                onClick={startDeleteMode}
              >
                Manage Delete
              </button>
            ) : (
              <button
                type="button"
                className="secondary-btn"
                onClick={cancelDeleteMode}
              >
                Cancel Delete Mode
              </button>
            )}
          </div>
        </div>
      </section>

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      {!loading && filteredItems.length > 0 && deleteMode && (
        <section className="card-like top-gap-sm escalation-delete-toolbar">
          <div className="row-between wrap-gap">
            <div>
              <p className="eyebrow">Delete Mode</p>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={toggleSelectAll}
                />
                <span>
                  Select all {activeTab} escalations ({filteredItems.length})
                </span>
              </label>
            </div>

            <div className="button-group wrap-gap">
              <button
                type="button"
                className="secondary-btn"
                onClick={() => setSelectedIds([])}
                disabled={selectedVisibleIds.length === 0}
              >
                Clear Selected
              </button>

              <button
                type="button"
                className="danger-btn"
                onClick={openBulkDeleteModal}
                disabled={selectedVisibleIds.length === 0}
              >
                Delete Selected ({selectedVisibleIds.length})
              </button>
            </div>
          </div>
        </section>
      )}

      {loading ? (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading escalations...</p>
        </section>
      ) : filteredItems.length === 0 ? (
        <section className="card-like top-gap-sm">
          <h3>
            {activeTab === 'pending'
              ? 'No pending escalations'
              : activeTab === 'resolved'
                ? 'No resolved escalations'
                : 'No deleted escalations'}
          </h3>

          <p className="muted">
            {activeTab === 'pending'
              ? 'Low-confidence AI questions will appear here for Team Lead or Manager review.'
              : activeTab === 'resolved'
                ? 'Resolved escalation questions will appear here after a manual answer is submitted.'
                : 'Deleted escalation questions will appear here and can be restored when needed.'}
          </p>
        </section>
      ) : (
        <div className="stack-gap top-gap-sm">
          {filteredItems.map((item) => (
            <article
              key={item.escalation_id}
              className={
                deleteMode && selectedIds.includes(item.escalation_id)
                  ? 'card-like escalation-card selected'
                  : 'card-like escalation-card'
              }
            >
              <div className="row-between wrap-gap">
                <div className="escalation-title-row">
                  {deleteMode && (
                    <label className="checkbox-row escalation-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(item.escalation_id)}
                        onChange={() => toggleSelectOne(item.escalation_id)}
                      />
                    </label>
                  )}

                  <div>
                    <p className="muted small">
                      Asked by {item.asked_by_name || 'Unknown Staff'}
                    </p>
                    <h3>{item.question}</h3>
                  </div>
                </div>

                <div className="row-gap">
                  <StatusBadge status={activeTab === 'trash' ? 'deleted' : item.status} />

                  {activeTab === 'trash' && (
                    <>
                      <button
                        type="button"
                        className="secondary-btn"
                        onClick={() => restoreEscalation(item.escalation_id)}
                      >
                        Restore
                      </button>

                      <button
                        type="button"
                        className="danger-btn"
                        onClick={() => permanentDeleteEscalation(item.escalation_id)}
                      >
                        Delete Forever
                      </button>
                    </>
                  )}
                </div>
              </div>

              {item.image_url ? (
                <div className="card-like top-gap-sm">
                  <p className="eyebrow">Uploaded Image</p>

                  <img
                    src={buildImageUrl(item.image_url)}

                    alt="Escalated upload"
                    style={{
                      width: '100%',
                      maxWidth: '260px',
                      maxHeight: '260px',
                      objectFit: 'contain',
                      borderRadius: '12px',
                      border: '1px solid var(--border)',
                      background: '#fff',
                      display: 'block',
                    }}
                    onError={(event) => {
                      console.log('Escalation image failed:', item.image_url);
                      event.currentTarget.style.display = 'none';
                    }}
                  />

                  <p className="muted small" style={{ marginTop: '0.5rem' }}>
                    {item.image_type || 'Uploaded image'}
                  </p>
                </div>
              ) : null}

              <div className="card-like top-gap-sm">
                <p className="eyebrow">AI Answer</p>
                <p>{item.ai_answer || 'No AI answer recorded.'}</p>
                <p className="muted small">
                  Score: {item.ai_score || 0} | Source: {item.ai_source || 'unknown'}
                </p>
              </div>

              {activeTab === 'pending' ? (
                <>
                  <textarea
                    rows="4"
                    value={answers[item.escalation_id] || ''}
                    onChange={(event) =>
                      updateAnswer(item.escalation_id, event.target.value)
                    }
                    placeholder="Write a manual answer for this escalated question"
                  />

                  <div className="escalation-answer-image-upload">
                    <label className="escalation-upload-btn">
                      <span className="escalation-upload-icon">
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <rect x="3" y="3" width="18" height="18" rx="3" />
                          <circle cx="8.5" cy="8.5" r="1.5" />
                          <path d="M21 15l-5-5L5 21" />
                        </svg>
                      </span>

                      <span>Upload answer image</span>

                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
                        style={{ display: 'none' }}
                        onChange={(event) => {
                          const file = event.target.files?.[0];

                          setAnswerImages((prev) => ({
                            ...prev,
                            [item.escalation_id]: file || null,
                          }));
                        }}
                      />
                    </label>

                    {answerImages[item.escalation_id] ? (
                      <div className="answer-image-preview-box">
                        <p className="muted small">
                          Selected image: {answerImages[item.escalation_id].name}
                        </p>

                        <img
                          src={URL.createObjectURL(answerImages[item.escalation_id])}
                          alt="Answer preview"
                          className="answer-image-preview"
                        />
                      </div>
                    ) : null}
                  </div>

                  <div className="row-between wrap-gap top-gap">
                    <p className="muted small">
                      After submitting, this question will move to the resolved tab.
                    </p>

                    <button
                      type="button"
                      className="primary-btn"
                      onClick={() => submitAnswer(item.escalation_id)}
                    >
                      Submit Manual Answer
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="card-like top-gap-sm">
                    <p className="eyebrow">Manual Answer</p>
                    <p>{item.manual_answer || 'No manual answer recorded.'}</p>
                  </div>

                  {item.image_url ? (
                    <div className="card-like top-gap-sm">
                      <p className="eyebrow">Related Image</p>

                      <img
                        src={buildImageUrl(item.image_url)}
                        alt="Resolved escalation upload"
                        style={{
                          width: '100%',
                          maxWidth: '260px',
                          maxHeight: '260px',
                          objectFit: 'contain',
                          borderRadius: '12px',
                          border: '1px solid var(--border)',
                          background: '#fff',
                          display: 'block',
                        }}
                        onError={(event) => {
                          console.log('Resolved escalation image failed:', buildImageUrl(item.image_url));
                          event.currentTarget.style.display = 'none';
                        }}
                      />

                      <p className="muted small" style={{ marginTop: '0.5rem' }}>
                        {item.image_type || 'Uploaded image'}
                      </p>
                    </div>
                  ) : null}

                  <p className="muted small top-gap">
                    Resolved at: {item.resolved_at || 'Not recorded'}
                  </p>
                </>
              )}
            </article>
          ))}
        </div>
      )}

      {bulkDeleteOpen && (
        <div className="delete-modal-overlay">
          <div className="delete-modal-card">
            <button
              type="button"
              className="delete-modal-close"
              onClick={closeBulkDeleteModal}
              disabled={bulkDeleting}
            >
              ×
            </button>

            <div className="delete-modal-icon-wrap">
              <div className="delete-modal-icon">
                <svg
                  width="42"
                  height="42"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 6h18" />
                  <path d="M8 6V4h8v2" />
                  <path d="M19 6l-1 14H6L5 6" />
                  <path d="M10 11v6" />
                  <path d="M14 11v6" />
                </svg>
              </div>
            </div>

            <div className="delete-modal-content">
              <h2>Move selected escalations to Trash Bin?</h2>
              <p>
                This will move {selectedVisibleIds.length} selected escalation(s) to the Trash Bin.
                You can restore them later if needed.
              </p>

              <div className="delete-modal-question">
                <strong>Selected:</strong> {selectedVisibleIds.length} escalation(s)
              </div>

              <div className="delete-modal-actions">
                <button
                  type="button"
                  className="delete-cancel-btn"
                  onClick={closeBulkDeleteModal}
                  disabled={bulkDeleting}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  className="delete-confirm-btn"
                  onClick={confirmBulkDelete}
                  disabled={bulkDeleting}
                >
                  {bulkDeleting ? 'Moving...' : 'Move to Trash Bin'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
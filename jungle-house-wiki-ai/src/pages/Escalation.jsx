import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Escalation() {
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [answers, setAnswers] = useState({});
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
      const response = await api.get('/escalations');
      const data = Array.isArray(response.data) ? response.data : [];

      setItems(data);

      const answerMap = {};
      data.forEach((item) => {
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

  const filteredItems = activeTab === 'pending' ? pendingItems : resolvedItems;

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

    if (!manualAnswer || !manualAnswer.trim()) {
      setMessage('Please write a manual answer before submitting.');
      return;
    }

    try {
      setMessage('');

      await api.put(`/escalations/${id}/answer`, {
        manual_answer: manualAnswer.trim(),
        handled_by: user?.user_id || null,
      });

      setMessage('Manual answer submitted successfully.');
      setActiveTab('resolved');
      setDeleteMode(false);
      setSelectedIds([]);
      fetchEscalations();
    } catch (error) {
      console.error('Submit manual answer error:', error);
      setMessage('Failed to submit manual answer.');
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
        selectedVisibleIds.map((id) => api.delete(`/escalations/${id}`))
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

      setMessage(`${selectedVisibleIds.length} escalation(s) deleted successfully.`);
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
              : 'No resolved escalations'}
          </h3>
          <p className="muted">
            {activeTab === 'pending'
              ? 'Low-confidence AI questions will appear here for Team Lead or Manager review.'
              : 'Resolved escalation questions will appear here after a manual answer is submitted.'}
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
                  <StatusBadge status={item.status} />
                </div>
              </div>

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
              <h2>Delete selected escalations?</h2>
              <p>
                This will permanently remove {selectedVisibleIds.length} selected escalation(s)
                from the system.
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
                  {bulkDeleting ? 'Deleting...' : 'Delete Selected'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
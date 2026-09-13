import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const NAV_ITEMS = [
  { key: 'all', label: 'All Users' },
  { key: 'pending', label: 'Pending' },
  { key: 'activation', label: 'Activation' },
  { key: 'active', label: 'Active' },
  { key: 'keys', label: 'Keys' },
  { key: 'email', label: 'Email Test' },
];

export default function UserManagement() {
  const { user } = useAuth();

  const actorId = user?.id || user?.user_id || null;
  const actorRole = String(user?.role || '').toLowerCase().replace(/[\s_-]/g, '');
  const isManagerActor = actorRole === 'manager' || actorRole === 'admin';

  const [users, setUsers] = useState([]);
  const [registrationKeys, setRegistrationKeys] = useState([]);

  const [loading, setLoading] = useState(true);
  const [keysLoading, setKeysLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);

  const [activeView, setActiveView] = useState('all');
  const [search, setSearch] = useState('');

  const [message, setMessage] = useState('');
  const [keyMessage, setKeyMessage] = useState('');
  const [emailTestMessage, setEmailTestMessage] = useState('');

  const [emailTestLoading, setEmailTestLoading] = useState(false);
  const [testRecipient, setTestRecipient] = useState(user?.email || '');

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get('/admin/users');
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch users error:', error);
      setMessage(error.response?.data?.message || 'Unable to load users.');
    } finally {
      setLoading(false);
    }
  };

  const fetchRegistrationKeys = async () => {
    if (!actorId) return;

    try {
      setKeysLoading(true);
      const response = await api.get('/registration-keys', {
        params: { actor_id: actorId },
      });
      setRegistrationKeys(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch registration keys error:', error);
      setKeyMessage(error.response?.data?.message || 'Unable to load activation keys.');
    } finally {
      setKeysLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    fetchRegistrationKeys();
  }, [actorId]);

  const getStage = (item) => {
    if (item.status === 'pending' && item.awaiting_activation) return 'activation';
    if (item.status === 'pending') return 'pending';
    if (item.status === 'active') return 'active';
    if (item.status === 'inactive') return 'inactive';
    if (item.status === 'declined') return 'declined';
    return String(item.status || 'unknown').toLowerCase();
  };

  const counts = useMemo(() => ({
    all: users.length,
    pending: users.filter((item) => getStage(item) === 'pending').length,
    activation: users.filter((item) => getStage(item) === 'activation').length,
    active: users.filter((item) => getStage(item) === 'active').length,
  }), [users]);

  const filteredUsers = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return users.filter((item) => {
      const stage = getStage(item);

      const viewMatches =
        activeView === 'all' ||
        (activeView === 'pending' && stage === 'pending') ||
        (activeView === 'activation' && stage === 'activation') ||
        (activeView === 'active' && stage === 'active');

      if (!viewMatches) return false;
      if (!keyword) return true;

      return [item.full_name, item.email, item.role_name, stage]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [users, activeView, search]);

  const updateUserStatus = async (userId, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';

    try {
      setActionLoadingId(userId);
      await api.put(`/admin/users/${userId}/status`, {
        status: newStatus,
        actor_id: actorId,
      });
      setMessage(newStatus === 'active' ? 'User activated.' : 'User deactivated.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Unable to update user status.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const updateUserRole = async (userId, newRole) => {
    try {
      setActionLoadingId(userId);
      await api.put(`/admin/users/${userId}/role`, {
        role: newRole,
        actor_id: actorId,
      });
      setMessage('Role updated.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Unable to update role.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const approveUser = async (userId, roleName) => {
    if (!window.confirm('Approve this registration and send the activation key?')) return;

    try {
      setActionLoadingId(userId);

      const response = await api.put(
        `/admin/registration-requests/${userId}/approve`,
        {
          role:
            String(roleName || 'staff').toLowerCase() === 'teamlead'
              ? 'teamlead'
              : 'staff',
          approved_by: actorId,
        }
      );

      setMessage(response.data?.message || 'Registration approved.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } catch (error) {
      setMessage(error.response?.data?.message || 'Approval failed.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } finally {
      setActionLoadingId(null);
    }
  };

  const declineUser = async (userId) => {
    const reason = window.prompt('Decline reason (optional)');
    if (reason === null) return;

    if (!window.confirm('Remove this pending registration?')) return;

    try {
      setActionLoadingId(userId);

      const response = await api.put(
        `/admin/registration-requests/${userId}/decline`,
        {
          reason,
          declined_by: actorId,
        }
      );

      setMessage(response.data?.message || 'Registration declined.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } catch (error) {
      setMessage(error.response?.data?.message || 'Decline failed.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const testSystemEmail = async () => {
    if (!actorId || !testRecipient.trim()) return;

    try {
      setEmailTestLoading(true);
      setEmailTestMessage('');

      const response = await api.post('/admin/email/test', {
        actor_id: actorId,
        email: testRecipient.trim().toLowerCase(),
      });

      setEmailTestMessage(response.data?.message || 'Test email sent.');
    } catch (error) {
      setEmailTestMessage(error.response?.data?.message || 'Email test failed.');
    } finally {
      setEmailTestLoading(false);
    }
  };

  const resendKey = async (keyId) => {
    try {
      setKeyMessage('');

      const response = await api.post(`/registration-keys/${keyId}/resend`, {
        actor_id: actorId,
      });

      setKeyMessage(response.data?.message || 'Activation key resent.');
      await fetchRegistrationKeys();
    } catch (error) {
      setKeyMessage(error.response?.data?.message || 'Resend failed.');
    }
  };

  const revokeKey = async (keyId) => {
    if (!window.confirm('Revoke this activation key?')) return;

    try {
      const response = await api.put(`/registration-keys/${keyId}/revoke`, {
        actor_id: actorId,
      });

      setKeyMessage(response.data?.message || 'Activation key revoked.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } catch (error) {
      setKeyMessage(error.response?.data?.message || 'Revoke failed.');
    }
  };

  const getInitials = (name) => {
    return String(name || 'U')
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');
  };

  const stageLabel = (stage) => {
    if (stage === 'activation') return 'Awaiting Key';
    if (stage === 'pending') return 'Pending';
    if (stage === 'active') return 'Active';
    if (stage === 'inactive') return 'Inactive';
    if (stage === 'declined') return 'Declined';
    return stage;
  };

  const isUserView = ['all', 'pending', 'activation', 'active'].includes(activeView);

  return (
    <div className="user-management-page professional">
      <PageHeader title="User Management" subtitle="Staff accounts and access control." />

      <section className="um-summary-grid">
        <button
          type="button"
          className={`um-summary-card ${activeView === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveView('pending')}
        >
          <span className="um-summary-label">Pending</span>
          <strong>{counts.pending}</strong>
          <span className="um-summary-meta">Needs review</span>
        </button>

        <button
          type="button"
          className={`um-summary-card ${activeView === 'activation' ? 'active' : ''}`}
          onClick={() => setActiveView('activation')}
        >
          <span className="um-summary-label">Activation</span>
          <strong>{counts.activation}</strong>
          <span className="um-summary-meta">Waiting for key</span>
        </button>

        <button
          type="button"
          className={`um-summary-card ${activeView === 'active' ? 'active' : ''}`}
          onClick={() => setActiveView('active')}
        >
          <span className="um-summary-label">Active</span>
          <strong>{counts.active}</strong>
          <span className="um-summary-meta">Can sign in</span>
        </button>

        <button
          type="button"
          className={`um-summary-card ${activeView === 'all' ? 'active' : ''}`}
          onClick={() => setActiveView('all')}
        >
          <span className="um-summary-label">Total</span>
          <strong>{counts.all}</strong>
          <span className="um-summary-meta">All accounts</span>
        </button>
      </section>

      <section className="um-workspace">
        <div className="um-workspace-head">
          <nav className="um-nav" aria-label="User management sections">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={activeView === item.key ? 'active' : ''}
                onClick={() => {
                  setActiveView(item.key);
                  setMessage('');
                  setKeyMessage('');
                  setEmailTestMessage('');
                }}
              >
                {item.label}
                {item.key === 'pending' && counts.pending > 0 ? (
                  <span className="um-nav-count">{counts.pending}</span>
                ) : null}
              </button>
            ))}
          </nav>

          {isUserView ? (
            <input
              className="um-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name or email"
              aria-label="Search users"
            />
          ) : null}
        </div>

        {message && isUserView ? (
          <div className="um-feedback">{message}</div>
        ) : null}

        {isUserView ? (
          <>
            {loading ? (
              <div className="um-empty-state">Loading users...</div>
            ) : filteredUsers.length === 0 ? (
              <div className="um-empty-state">
                <strong>No users found</strong>
                <span>Try another filter or search.</span>
              </div>
            ) : (
              <div className="um-table-wrap">
                <table className="um-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Joined</th>
                      <th>Action</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredUsers.map((item) => {
                      const isManager =
                        String(item.role_name || '').toLowerCase() === 'manager';
                      const isPending = item.status === 'pending';
                      const awaitingActivation =
                        isPending && item.awaiting_activation;
                      const isBusy = actionLoadingId === item.user_id;
                      const stage = getStage(item);

                      return (
                        <tr key={item.user_id}>
                          <td>
                            <div className="um-user">
                              <div className="um-avatar">{getInitials(item.full_name)}</div>
                              <div className="um-user-copy">
                                <strong>{item.full_name}</strong>
                                <span>{item.email}</span>
                              </div>
                            </div>
                          </td>

                          <td>
                            {isManager ? (
                              <span className="um-role-tag manager">Manager</span>
                            ) : isManagerActor ? (
                              <select
                                className="um-role-select"
                                value={item.role_name}
                                onChange={(event) =>
                                  updateUserRole(item.user_id, event.target.value)
                                }
                                disabled={isBusy}
                              >
                                <option value="staff">Staff</option>
                                <option value="teamlead">Team Lead</option>
                              </select>
                            ) : (
                              <span className="um-role-tag">{item.role_name}</span>
                            )}
                          </td>

                          <td>
                            <span className={`um-status-tag ${stage}`}>
                              <i />
                              {stageLabel(stage)}
                            </span>
                          </td>

                          <td>
                            <span className="um-date">{item.created_at || '-'}</span>
                          </td>

                          <td>
                            <div className="um-row-actions">
                              {isManager ? (
                                <span className="um-protected">Protected</span>
                              ) : isPending ? (
                                <>
                                  {!awaitingActivation ? (
                                    <button
                                      type="button"
                                      className="um-action-btn primary"
                                      disabled={isBusy}
                                      onClick={() =>
                                        approveUser(item.user_id, item.role_name)
                                      }
                                    >
                                      {isBusy ? 'Working...' : 'Approve'}
                                    </button>
                                  ) : (
                                    <span className="um-key-state">Key sent</span>
                                  )}

                                  <button
                                    type="button"
                                    className="um-action-btn danger"
                                    disabled={isBusy}
                                    onClick={() => declineUser(item.user_id)}
                                  >
                                    Decline
                                  </button>
                                </>
                              ) : item.status === 'declined' ? (
                                <span className="um-muted">—</span>
                              ) : isManagerActor ? (
                                <button
                                  type="button"
                                  className={`um-action-btn ${
                                    item.status === 'active' ? 'danger-soft' : 'secondary'
                                  }`}
                                  disabled={isBusy}
                                  onClick={() =>
                                    updateUserStatus(item.user_id, item.status)
                                  }
                                >
                                  {item.status === 'active' ? 'Deactivate' : 'Activate'}
                                </button>
                              ) : (
                                <span className="um-muted">—</span>
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
          </>
        ) : null}

        {activeView === 'email' ? (
          <div className="um-tool-panel">
            <div className="um-tool-head">
              <div>
                <span className="um-tool-kicker">System Email</span>
                <h3>Send test email</h3>
              </div>
            </div>

            <div className="um-email-form">
              <input
                type="email"
                value={testRecipient}
                onChange={(event) => {
                  setTestRecipient(event.target.value);
                  setEmailTestMessage('');
                }}
                placeholder="Recipient email"
              />

              <button
                type="button"
                className="um-action-btn primary"
                onClick={testSystemEmail}
                disabled={
                  emailTestLoading || !actorId || !testRecipient.trim()
                }
              >
                {emailTestLoading ? 'Sending...' : 'Send Test'}
              </button>
            </div>

            {emailTestMessage ? (
              <div className="um-feedback">{emailTestMessage}</div>
            ) : null}
          </div>
        ) : null}

        {activeView === 'keys' ? (
          <div className="um-tool-panel">
            <div className="um-tool-head">
              <div>
                <span className="um-tool-kicker">Security</span>
                <h3>Activation keys</h3>
              </div>
              <span className="um-record-count">{registrationKeys.length} records</span>
            </div>

            {keyMessage ? (
              <div className="um-feedback">{keyMessage}</div>
            ) : null}

            {keysLoading ? (
              <div className="um-empty-state">Loading keys...</div>
            ) : registrationKeys.length === 0 ? (
              <div className="um-empty-state">
                <strong>No activation keys</strong>
                <span>Keys appear after account approval.</span>
              </div>
            ) : (
              <div className="um-table-wrap">
                <table className="um-table um-key-table">
                  <thead>
                    <tr>
                      <th>Key</th>
                      <th>Email</th>
                      <th>Status</th>
                      <th>Attempts</th>
                      <th>Sent</th>
                      <th>Used</th>
                      <th>Action</th>
                    </tr>
                  </thead>

                  <tbody>
                    {registrationKeys.map((key) => (
                      <tr key={key.key_id}>
                        <td>
                          <code className="um-key-code">{key.key_preview || '-'}</code>
                        </td>
                        <td>{key.assigned_email || key.used_by_email || '-'}</td>
                        <td>
                          <span className={`um-status-tag ${String(key.status || '').toLowerCase()}`}>
                            <i />
                            {key.status || '-'}
                          </span>
                        </td>
                        <td>{key.failed_attempts || 0}/3</td>
                        <td><span className="um-date">{key.email_sent_at || 'Not sent'}</span></td>
                        <td><span className="um-date">{key.used_at || '-'}</span></td>
                        <td>
                          {key.status === 'unused' ? (
                            <div className="um-row-actions">
                              <button
                                type="button"
                                className="um-action-btn secondary"
                                onClick={() => resendKey(key.key_id)}
                              >
                                Resend
                              </button>
                              <button
                                type="button"
                                className="um-action-btn danger"
                                onClick={() => revokeKey(key.key_id)}
                              >
                                Revoke
                              </button>
                            </div>
                          ) : (
                            <span className="um-muted">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const NAV_ITEMS = [
  { key: 'all', label: 'All Users' },
  { key: 'pending', label: 'Pending' },
  { key: 'active', label: 'Active' },
  { key: 'inactive', label: 'Inactive' },
];

const getStage = (item) => String(item?.status || 'unknown').trim().toLowerCase();
const normaliseRole = (role) => String(role || '').trim().toLowerCase().replace(/[\s_-]/g, '');

export default function UserManagement() {
  const { user } = useAuth();

  const actorId = user?.id ?? user?.user_id ?? null;
  const actorRole = normaliseRole(user?.role);
  const isManagerActor = actorRole === 'manager' || actorRole === 'admin';
  const isApproverActor = isManagerActor || actorRole === 'teamlead';

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [activeView, setActiveView] = useState('all');
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');
  // This is an explicit declaration by the reviewer, NOT identity verification
  // performed by the browser. The backend remains responsible for enforcement.
  const [verifiedUserIds, setVerifiedUserIds] = useState(() => new Set());

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

  // Preserve the original load-on-mount behavior. The protected route and
  // backend session/role checks control access; this page does not trust an ID
  // from a browser storage object to authorize a request.
  useEffect(() => {
    fetchUsers();
  }, []);

  const counts = useMemo(() => ({
    all: users.length,
    pending: users.filter((item) => getStage(item) === 'pending').length,
    active: users.filter((item) => getStage(item) === 'active').length,
    inactive: users.filter((item) => getStage(item) === 'inactive').length,
  }), [users]);

  const filteredUsers = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return users.filter((item) => {
      const stage = getStage(item);
      if (activeView !== 'all' && stage !== activeView) return false;
      if (!keyword) return true;

      return [item.full_name, item.email, item.role_name, stage]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [users, activeView, search]);

  const setIdentityVerified = (userId, checked) => {
    setVerifiedUserIds((previous) => {
      const next = new Set(previous);
      if (checked) next.add(String(userId));
      else next.delete(String(userId));
      return next;
    });
  };

  const updateUserStatus = async (userId, currentStatus) => {
    if (!isManagerActor || actorId == null) return;
    const newStatus = getStage({ status: currentStatus }) === 'active' ? 'inactive' : 'active';

    try {
      setActionLoadingId(userId);
      setMessage('');
      // Compatibility with the CURRENT Flask route, which still requires
      // actor_id. The server verifies it matches the signed-in session;
      // this value must never be treated as proof of authorization.
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
    if (!isManagerActor || actorId == null) return;

    try {
      setActionLoadingId(userId);
      setMessage('');
      // Required for compatibility with the uploaded backend until its role
      // endpoint is refactored to derive the actor exclusively from session.
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

  const approveUser = async (item) => {
    if (!isApproverActor || actorId == null) return;
    const userId = item.user_id;
    if (!verifiedUserIds.has(String(userId))) {
      setMessage('Verify the applicant’s identity using a trusted staff record or independent contact first.');
      return;
    }

    const approvedRole = normaliseRole(item.role_name) === 'teamlead' ? 'teamlead' : 'staff';
    if (approvedRole === 'teamlead' && !isManagerActor) {
      setMessage('Only a Manager can approve an account with the Team Lead role.');
      return;
    }

    if (!window.confirm(
      `Confirm you independently verified ${item.full_name || item.email} and approve this account? The user will be able to sign in immediately.`
    )) return;

    try {
      setActionLoadingId(userId);
      setMessage('');
      // The backend reads the approver from the signed Flask session. Never
      // send approved_by or another identity supplied by the browser.
      const response = await api.put(
        `/admin/registration-requests/${userId}/approve`,
        { role: approvedRole, identity_verified: true }
      );
      setIdentityVerified(userId, false);
      setMessage(response.data?.message || 'Registration approved. The user can now sign in.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Approval failed.');
      // A parallel reviewer may have changed this record in the meantime.
      await fetchUsers();
    } finally {
      setActionLoadingId(null);
    }
  };

  const declineUser = async (item) => {
    if (!isApproverActor || actorId == null) return;
    const reason = window.prompt('Decline reason (optional)');
    if (reason === null) return;

    if (!window.confirm(
      `Decline and permanently remove the pending registration for ${item.full_name || item.email}? This cannot be undone.`
    )) return;

    const userId = item.user_id;
    try {
      setActionLoadingId(userId);
      setMessage('');
      const response = await api.put(
        `/admin/registration-requests/${userId}/decline`,
        { reason: reason.trim().slice(0, 500) }
      );
      setIdentityVerified(userId, false);
      setMessage(response.data?.message || 'Registration declined.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Decline failed.');
      await fetchUsers();
    } finally {
      setActionLoadingId(null);
    }
  };

  const getInitials = (name) => String(name || 'U')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  const stageLabel = (stage) => {
    if (stage === 'pending') return 'Pending';
    if (stage === 'active') return 'Active';
    if (stage === 'inactive') return 'Inactive';
    if (stage === 'declined') return 'Declined';
    return stage;
  };

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
          className={`um-summary-card ${activeView === 'inactive' ? 'active' : ''}`}
          onClick={() => setActiveView('inactive')}
        >
          <span className="um-summary-label">Inactive</span>
          <strong>{counts.inactive}</strong>
          <span className="um-summary-meta">Access disabled</span>
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
                }}
              >
                {item.label}
                {item.key === 'pending' && counts.pending > 0 ? (
                  <span className="um-nav-count">{counts.pending}</span>
                ) : null}
              </button>
            ))}
          </nav>

          <input
            className="um-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name or email"
            aria-label="Search users"
          />
        </div>

        {message ? <div className="um-feedback" role="status">{message}</div> : null}

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
                  const isManager = ['manager', 'admin'].includes(normaliseRole(item.role_name));
                  const isPending = getStage(item) === 'pending';
                  const isBusy = actionLoadingId !== null;
                  const stage = getStage(item);
                  const isVerified = verifiedUserIds.has(String(item.user_id));
                  const roleIsTeamLead = normaliseRole(item.role_name) === 'teamlead';

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
                          <span className="um-role-tag manager">{item.role_name}</span>
                        ) : isManagerActor ? (
                          <select
                            className="um-role-select"
                            value={roleIsTeamLead ? 'teamlead' : 'staff'}
                            onChange={(event) => updateUserRole(item.user_id, event.target.value)}
                            disabled={isBusy}
                            aria-label={`Role for ${item.full_name || item.email}`}
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
                          ) : isPending && isApproverActor ? (
                            <>
                              <label className="um-verify-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <input
                                  type="checkbox"
                                  checked={isVerified}
                                  onChange={(event) => setIdentityVerified(item.user_id, event.target.checked)}
                                  disabled={isBusy}
                                  aria-label={`I independently verified the identity of ${item.full_name || item.email}`}
                                />
                                Identity verified
                              </label>
                              <button
                                type="button"
                                className="um-action-btn primary"
                                disabled={isBusy || !isVerified || (roleIsTeamLead && !isManagerActor)}
                                title={roleIsTeamLead && !isManagerActor ? 'Only Managers can approve Team Lead accounts' : undefined}
                                onClick={() => approveUser(item)}
                              >
                                {actionLoadingId === item.user_id ? 'Working...' : 'Approve'}
                              </button>
                              <button
                                type="button"
                                className="um-action-btn danger"
                                disabled={isBusy}
                                onClick={() => declineUser(item)}
                              >
                                Decline
                              </button>
                            </>
                          ) : stage === 'declined' || isPending ? (
                            <span className="um-muted">—</span>
                          ) : isManagerActor ? (
                            <button
                              type="button"
                              className={`um-action-btn ${stage === 'active' ? 'danger-soft' : 'secondary'}`}
                              disabled={isBusy}
                              onClick={() => updateUserStatus(item.user_id, stage)}
                            >
                              {stage === 'active' ? 'Deactivate' : 'Activate'}
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
      </section>
    </div>
  );
}

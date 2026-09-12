import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import StatusBadge from '../../components/StatusBadge';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export default function UserManagement() {
  const { user } = useAuth();
  const actorId = user?.id || user?.user_id || null;
  const actorRole = String(user?.role || '').toLowerCase().replace(/[\s_-]/g, '');
  const isManagerActor = actorRole === 'manager' || actorRole === 'admin';

  const [users, setUsers] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [registrationKeys, setRegistrationKeys] = useState([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [keyMessage, setKeyMessage] = useState('');

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get('/admin/users');
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch users error:', error);
      setMessage(error.response?.data?.message || 'Failed to load users.');
    } finally {
      setLoading(false);
    }
  };

  const fetchRegistrationKeys = async () => {
    if (!actorId) return;
    try {
      setKeysLoading(true);
      const response = await api.get('/registration-keys', { params: { actor_id: actorId } });
      setRegistrationKeys(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch registration keys error:', error);
      setKeyMessage(error.response?.data?.message || 'Failed to load registration key audit.');
    } finally {
      setKeysLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);
  // actorId is the intended trigger; fetchRegistrationKeys reads the latest actorId.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchRegistrationKeys(); }, [actorId]);

  const updateUserStatus = async (userId, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
    try {
      await api.put(`/admin/users/${userId}/status`, { status: newStatus, actor_id: actorId });
      setMessage(`User status updated to ${newStatus}.`);
      fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Failed to update user status.');
    }
  };

  const updateUserRole = async (userId, newRole) => {
    try {
      await api.put(`/admin/users/${userId}/role`, { role: newRole, actor_id: actorId });
      setMessage(`User role updated to ${newRole}.`);
      fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Failed to update user role.');
    }
  };

  const approveUser = async (userId, roleName) => {
    if (!window.confirm('Approve this registration? A one-time registration key will be generated and emailed automatically.')) return;

    try {
      setActionLoadingId(userId);
      const response = await api.put(`/admin/registration-requests/${userId}/approve`, {
        role: String(roleName || 'staff').toLowerCase() === 'teamlead' ? 'teamlead' : 'staff',
        approved_by: actorId,
      });
      setMessage(response.data?.message || 'Registration approved successfully.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } catch (error) {
      setMessage(error.response?.data?.message || 'Failed to approve user registration.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const declineUser = async (userId) => {
    const reason = window.prompt('Reason for declining this registration? You can leave it empty.');
    if (reason === null) return;
    if (!window.confirm('Decline this registration? The user will receive a decision email and will not be able to enter the system.')) return;

    try {
      setActionLoadingId(userId);
      const response = await api.put(`/admin/registration-requests/${userId}/decline`, {
        reason,
        declined_by: actorId,
      });
      setMessage(response.data?.message || 'Registration declined successfully.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } catch (error) {
      setMessage(error.response?.data?.message || 'Failed to decline user registration.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const resendKey = async (keyId) => {
    try {
      setKeyMessage('');
      const response = await api.post(`/registration-keys/${keyId}/resend`, { actor_id: actorId });
      setKeyMessage(response.data?.message || 'Activation key resent.');
      fetchRegistrationKeys();
    } catch (error) {
      setKeyMessage(error.response?.data?.message || 'Failed to resend activation key.');
    }
  };

  const revokeKey = async (keyId) => {
    if (!window.confirm('Revoke this unused activation key? It will stop working immediately.')) return;
    try {
      const response = await api.put(`/registration-keys/${keyId}/revoke`, { actor_id: actorId });
      setKeyMessage(response.data?.message || 'Activation key revoked.');
      await Promise.all([fetchUsers(), fetchRegistrationKeys()]);
    } catch (error) {
      setKeyMessage(error.response?.data?.message || 'Failed to revoke activation key.');
    }
  };

  const pendingApprovalUsers = users.filter(
    (item) => item.status === 'pending' && !item.awaiting_activation
  );
  const awaitingActivationUsers = users.filter(
    (item) => item.status === 'pending' && item.awaiting_activation
  );

  return (
    <div>
      <PageHeader
        title="User Management"
        subtitle="Review registrations, approve or decline access, and monitor one-time activation keys."
      />

      <section className="card-like top-gap-sm" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
        <div>
          <p className="eyebrow">Pending Approval</p>
          <h2>{pendingApprovalUsers.length}</h2>
          <p className="muted">New registrations waiting for Manager / Team Leader review.</p>
        </div>
        <div>
          <p className="eyebrow">Awaiting Activation</p>
          <h2>{awaitingActivationUsers.length}</h2>
          <p className="muted">Approved accounts waiting for the user to enter the emailed key.</p>
        </div>
        <div>
          <p className="eyebrow">Total Users</p>
          <h2>{users.length}</h2>
          <p className="muted">All account records.</p>
        </div>
      </section>

      {message ? <section className="card-like top-gap-sm"><p className="muted">{message}</p></section> : null}

      {loading ? (
        <section className="card-like top-gap-sm"><p className="muted">Loading users...</p></section>
      ) : (
        <div className="table-card card-like top-gap-sm">
          <table>
            <thead>
              <tr>
                <th>User ID</th><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Registration Stage</th><th>Registered At</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => {
                const isManager = String(item.role_name).toLowerCase() === 'manager';
                const isPending = item.status === 'pending';
                const awaitingActivation = isPending && item.awaiting_activation;
                const isBusy = actionLoadingId === item.user_id;

                return (
                  <tr key={item.user_id}>
                    <td>{item.user_id}</td>
                    <td>{item.full_name}</td>
                    <td>{item.email}</td>
                    <td>
                      {isManager ? (
                        <span className="role-pill">manager</span>
                      ) : isManagerActor ? (
                        <select value={item.role_name} onChange={(event) => updateUserRole(item.user_id, event.target.value)} disabled={isBusy}>
                          <option value="staff">staff</option>
                          <option value="teamlead">teamlead</option>
                        </select>
                      ) : (
                        <span className="role-pill">{item.role_name}</span>
                      )}
                    </td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>
                      {awaitingActivation ? (
                        <span className="role-pill">Awaiting Activation</span>
                      ) : isPending ? (
                        <span className="role-pill">Pending Approval</span>
                      ) : item.status === 'active' ? (
                        <span className="role-pill">Access Active</span>
                      ) : item.status === 'declined' ? (
                        <span className="role-pill">Declined / Cancelled</span>
                      ) : (
                        <span className="role-pill">{item.status}</span>
                      )}
                    </td>
                    <td>{item.created_at || '-'}</td>
                    <td>
                      {isManager ? (
                        <button className="secondary-btn" disabled>Protected</button>
                      ) : isPending ? (
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          {!awaitingActivation ? (
                            <button className="primary-btn" type="button" disabled={isBusy} onClick={() => approveUser(item.user_id, item.role_name)}>
                              {isBusy ? 'Processing...' : 'Approve & Send Key'}
                            </button>
                          ) : (
                            <button className="secondary-btn" disabled>Key Issued</button>
                          )}
                          <button className="secondary-btn danger-btn" type="button" disabled={isBusy} onClick={() => declineUser(item.user_id)}>Decline</button>
                        </div>
                      ) : item.status === 'declined' ? (
                        <button className="secondary-btn" disabled>Declined</button>
                      ) : isManagerActor ? (
                        <button className={item.status === 'active' ? 'secondary-btn danger-btn' : 'secondary-btn'} disabled={isBusy} onClick={() => updateUserStatus(item.user_id, item.status)}>
                          {item.status === 'active' ? 'Deactivate' : 'Activate'}
                        </button>
                      ) : (
                        <button className="secondary-btn" disabled>Manager only</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {users.length === 0 ? <p className="muted top-gap">No users found.</p> : null}
        </div>
      )}

      <section className="card-like top-gap">
        <div>
          <h3>Activation Key Audit</h3>
          <p className="muted">Keys are generated automatically only after approval. Full key values are not displayed here.</p>
        </div>

        {keyMessage ? <p className="muted top-gap-sm">{keyMessage}</p> : null}

        {keysLoading ? (
          <p className="muted top-gap">Loading activation keys...</p>
        ) : registrationKeys.length === 0 ? (
          <p className="muted top-gap">No activation keys issued yet.</p>
        ) : (
          <div className="table-card top-gap">
            <table>
              <thead>
                <tr><th>Key</th><th>Email</th><th>Status</th><th>Failed Attempts</th><th>Issued By</th><th>Email Sent</th><th>Used At</th><th>Action</th></tr>
              </thead>
              <tbody>
                {registrationKeys.map((key) => (
                  <tr key={key.key_id}>
                    <td><code>{key.key_preview || '-'}</code></td>
                    <td>{key.assigned_email || key.used_by_email || '-'}</td>
                    <td><span className="role-pill">{key.status}</span></td>
                    <td>{key.failed_attempts || 0} / 3</td>
                    <td>{key.created_by_name || '-'}</td>
                    <td>{key.email_sent_at || 'Not sent'}</td>
                    <td>{key.used_at || '-'}</td>
                    <td>
                      {key.status === 'unused' ? (
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <button type="button" className="secondary-btn" onClick={() => resendKey(key.key_id)}>Resend</button>
                          <button type="button" className="secondary-btn danger-btn" onClick={() => revokeKey(key.key_id)}>Revoke</button>
                        </div>
                      ) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

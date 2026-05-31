import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import StatusBadge from '../../components/StatusBadge';
import api from '../../services/api';

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get('/admin/users');
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch users error:', error);
      setMessage('Failed to load users.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const updateUserStatus = async (userId, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';

    try {
      await api.put(`/admin/users/${userId}/status`, {
        status: newStatus,
      });

      setMessage(`User status updated to ${newStatus}.`);
      fetchUsers();
    } catch (error) {
      console.error('Update user status error:', error);
      setMessage('Failed to update user status.');
    }
  };

  const updateUserRole = async (userId, newRole) => {
    try {
      await api.put(`/admin/users/${userId}/role`, {
        role: newRole,
      });

      setMessage(`User role updated to ${newRole}.`);
      fetchUsers();
    } catch (error) {
      console.error('Update user role error:', error);
      setMessage('Failed to update user role.');
    }
  };

  const approveUser = async (userId) => {
    const confirmApprove = window.confirm(
      'Approve this user account? The user will be able to log in after approval.'
    );

    if (!confirmApprove) return;

    try {
      setActionLoadingId(userId);

      await api.put(`/admin/registration-requests/${userId}/approve`, {
        role: 'staff',
      });

      setMessage('User registration approved successfully.');
      fetchUsers();
    } catch (error) {
      console.error('Approve user error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to approve user registration.'
      );
    } finally {
      setActionLoadingId(null);
    }
  };

  const declineUser = async (userId) => {
    const reason = window.prompt(
      'Reason for declining this registration? You can leave it empty.'
    );

    if (reason === null) return;

    const confirmDecline = window.confirm(
      'Decline this user account? The user will not be able to log in.'
    );

    if (!confirmDecline) return;

    try {
      setActionLoadingId(userId);

      await api.put(`/admin/registration-requests/${userId}/decline`, {
        reason,
      });

      setMessage('User registration declined successfully.');
      fetchUsers();
    } catch (error) {
      console.error('Decline user error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to decline user registration.'
      );
    } finally {
      setActionLoadingId(null);
    }
  };

  const pendingUsers = users.filter((user) => user.status === 'pending');

  return (
    <div>
      <PageHeader
        title="User Management"
        subtitle="View users, approve new registrations, update roles, and activate or deactivate accounts."
      />

      <section
        className="card-like top-gap-sm"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '1rem',
        }}
      >
        <div>
          <p className="eyebrow">Pending Approval</p>
          <h2>{pendingUsers.length}</h2>
          <p className="muted">
            New accounts waiting for manager/team lead approval.
          </p>
        </div>

        <div>
          <p className="eyebrow">Total Users</p>
          <h2>{users.length}</h2>
          <p className="muted">All registered user accounts.</p>
        </div>
      </section>

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      {loading ? (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading users...</p>
        </section>
      ) : (
        <div className="table-card card-like top-gap-sm">
          <table>
            <thead>
              <tr>
                <th>User ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Email Verified</th>
                <th>Role</th>
                <th>Status</th>
                <th>Registered At</th>
                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              {users.map((user) => {
                const isManager = user.role_name === 'manager';
                const isPending = user.status === 'pending';
                const isBusy = actionLoadingId === user.user_id;

                return (
                  <tr key={user.user_id}>
                    <td>{user.user_id}</td>
                    <td>{user.full_name}</td>
                    <td>{user.email}</td>

                    <td>
                      {user.email_verified === true ||
                      user.email_verified === 1 ||
                      user.email_verified === '1' ? (
                        <span className="role-pill">Verified</span>
                      ) : (
                        <span className="role-pill">Not verified</span>
                      )}
                    </td>

                    <td>
                      {isManager ? (
                        <span className="role-pill">manager</span>
                      ) : (
                        <select
                          value={user.role_name}
                          onChange={(event) =>
                            updateUserRole(user.user_id, event.target.value)
                          }
                          disabled={isBusy}
                        >
                          <option value="staff">staff</option>
                          <option value="teamlead">teamlead</option>
                        </select>
                      )}
                    </td>

                    <td>
                      <StatusBadge status={user.status} />
                    </td>

                    <td>{user.created_at || '-'}</td>

                    <td>
                      {isManager ? (
                        <button className="secondary-btn" disabled>
                          Protected
                        </button>
                      ) : isPending ? (
                        <div
                          style={{
                            display: 'flex',
                            gap: '0.5rem',
                            flexWrap: 'wrap',
                          }}
                        >
                          <button
                            className="primary-btn"
                            type="button"
                            disabled={isBusy}
                            onClick={() => approveUser(user.user_id)}
                          >
                            {isBusy ? 'Processing...' : 'Approve'}
                          </button>

                          <button
                            className="secondary-btn danger-btn"
                            type="button"
                            disabled={isBusy}
                            onClick={() => declineUser(user.user_id)}
                          >
                            Decline
                          </button>
                        </div>
                      ) : user.status === 'declined' ? (
                        <button className="secondary-btn" disabled>
                          Declined
                        </button>
                      ) : (
                        <button
                          className={
                            user.status === 'active'
                              ? 'secondary-btn danger-btn'
                              : 'secondary-btn'
                          }
                          disabled={isBusy}
                          onClick={() =>
                            updateUserStatus(user.user_id, user.status)
                          }
                        >
                          {user.status === 'active'
                            ? 'Deactivate'
                            : 'Activate'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {users.length === 0 && (
            <p className="muted top-gap">No users found.</p>
          )}
        </div>
      )}
    </div>
  );
}
import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import StatusBadge from '../../components/StatusBadge';
import api from '../../services/api';

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);

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

  return (
    <div>
      <PageHeader
        title="User Management"
        subtitle="View users, update roles, and activate or deactivate accounts."
      />

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
                <th>Role</th>
                <th>Status</th>
                <th>Registered At</th>
                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td>{user.user_id}</td>
                  <td>{user.full_name}</td>
                  <td>{user.email}</td>

                  <td>
                    {user.role_name === 'manager' ? (
                      <span className="role-pill">manager</span>
                    ) : (
                      <select
                        value={user.role_name}
                        onChange={(event) =>
                          updateUserRole(user.user_id, event.target.value)
                        }
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
                    {user.role_name === 'manager' ? (
                      <button className="secondary-btn" disabled>
                        Protected
                      </button>
                    ) : (
                      <button
                        className={
                          user.status === 'active'
                            ? 'secondary-btn danger-btn'
                            : 'secondary-btn'
                        }
                        onClick={() =>
                          updateUserStatus(user.user_id, user.status)
                        }
                      >
                        {user.status === 'active' ? 'Deactivate' : 'Activate'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {users.length === 0 && <p className="muted top-gap">No users found.</p>}
        </div>
      )}
    </div>
  );
}
import PageHeader from '../../components/PageHeader';
import StatusBadge from '../../components/StatusBadge';


export default function UserManagement() {
  return (
    <div>
      <PageHeader
        title="User Management"
        subtitle="Create, update, activate, or deactivate accounts and assign roles."
      />

      <div className="table-card card-like">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {mockUsers.map((user) => (
              <tr key={user.id}>
                <td>{user.name}</td>
                <td>{user.email}</td>
                <td>{user.role}</td>
                <td><StatusBadge status={user.status} /></td>
                <td><button className="secondary-btn">Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
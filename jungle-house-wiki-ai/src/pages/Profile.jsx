import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';

export default function Profile() {
  const { user } = useAuth();

  return (
    <div>
      <PageHeader
        title="Profile"
        subtitle="Account details and basic activity visibility for the current user."
      />

      <div className="two-column-grid">
        <section className="card-like">
          <h3>Account Details</h3>
          <p><strong>Name:</strong> {user?.name}</p>
          <p><strong>Email:</strong> {user?.email}</p>
          <p><strong>Role:</strong> {user?.role}</p>
        </section>

        <section className="card-like">
          <h3>Login Activity</h3>
          <ul className="simple-list">
            <li>Last login: Just now</li>
            <li>Device: Browser session</li>
            <li>Status: Active</li>
          </ul>
        </section>
      </div>
    </div>
  );
}

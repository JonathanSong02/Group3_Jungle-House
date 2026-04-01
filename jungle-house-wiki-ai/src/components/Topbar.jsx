import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Topbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="topbar card-like">
      <div>
        <p className="muted small">Signed in as</p>
        <strong>{user?.name}</strong>
        <span className="role-pill">{user?.role}</span>
      </div>
      <button className="secondary-btn" onClick={handleLogout}>Logout</button>
    </header>
  );
}

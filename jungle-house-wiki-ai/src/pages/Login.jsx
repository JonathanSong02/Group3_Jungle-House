import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const [form, setForm] = useState({
    email: 'jonathan@example.com',
    password: '123456',
    role: 'staff',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || '/dashboard';

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      await login(form);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Unable to login.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card-like">
        <p className="eyebrow">Jungle House</p>
        <h1>AI-Powered Wiki Training Assistant</h1>
        <p className="muted">
          Temporary frontend login for development.
        </p>

        <form onSubmit={handleSubmit} className="form-stack">
          <label>
            Email
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              placeholder="Enter your email"
              required
            />
          </label>

          <label>
            Password
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={handleChange}
              placeholder="Enter your password"
              required
            />
          </label>

          <label>
            Role for testing
            <select name="role" value={form.role} onChange={handleChange}>
              <option value="staff">Staff</option>
              <option value="teamlead">Team Lead</option>
              <option value="manager">Manager</option>
            </select>
          </label>

          {error ? <p className="error-text">{error}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Login'}
          </button>

          <Link to="/register" className="text-link">
            Register new account
          </Link>
        </form>
      </div>
    </div>
  );
}
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const [form, setForm] = useState({
    email: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false); // UX: Toggle state

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || '/dashboard';

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const togglePasswordVisibility = () => {
    setShowPassword((prev) => !prev);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      await login({
        email: form.email.trim().toLowerCase(), // Security: Sanitize input
        password: form.password,
      });
      navigate(from, { replace: true });
    } catch (err) {
      // Security: Avoid logging full error objects which might contain sensitive request data
      console.error('LOGIN PAGE ERROR: Request failed.'); 
      setError(err.message || 'Unable to login. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card-like">
        <p className="eyebrow">Jungle House</p>
        <h1>Welcome Back</h1>
        <p className="muted">
          Sign in with your registered account to access the training assistant.
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
              autoComplete="username" // Security: Helps password managers
              required
            />
          </label>

          <label>
            <div className="row-between">
              <span>Password</span>
              <button 
                type="button" 
                onClick={togglePasswordVisibility}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.85rem', color: '#555' }}
                tabIndex="-1" // Keep out of standard tab flow so it doesn't interrupt typing
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            <input
              name="password"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              onChange={handleChange}
              placeholder="Enter your password"
              autoComplete="current-password" // Security: Helps password managers
              required
            />
          </label>

          {error ? <p className="error-text">{error}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Login'}
          </button>

          <div className="row-between wrap-gap top-gap">
            <Link to="/register" className="text-link">
              Register new account
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
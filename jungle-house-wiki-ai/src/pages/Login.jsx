import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/AuthSecurity.css';

function destinationFor(loggedInUser, requestedLocation) {
  const path = requestedLocation?.pathname;

  // Restore only an internal application route, never an external URL or
  // another trip to the login page. Preserve its query and hash, if present.
  if (
    typeof path === 'string' &&
    path.startsWith('/') &&
    !path.startsWith('//') &&
    !path.includes('\\') &&
    path !== '/login' &&
    !path.startsWith('/login/')
  ) {
    return `${path}${requestedLocation.search || ''}${requestedLocation.hash || ''}`;
  }

  const role = String(loggedInUser?.role || '')
    .toLowerCase()
    .replace(/[\s_-]/g, '');

  return role === 'manager' ? '/admin/dashboard' : '/dashboard';
}

export default function Login() {
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [dismissSessionMessage, setDismissSessionMessage] = useState(false);

  const { login, user, isAuthLoading, authError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const requestedLocation = location.state?.from;

  // A valid session may already have been restored when the user visits
  // /login. Wait for Flask's /auth/me response before redirecting.
  useEffect(() => {
    if (!isAuthLoading && String(user?.status || '').toLowerCase() === 'active') {
      navigate(destinationFor(user, requestedLocation), { replace: true });
    }
  }, [user, isAuthLoading, navigate, requestedLocation]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setError('');
    setInfo('');
    setDismissSessionMessage(true);
  };

  const handleCredentialsSubmit = async (event) => {
    event.preventDefault();
    if (loading || isAuthLoading) return;

    setLoading(true);
    setError('');
    setInfo('');
    setDismissSessionMessage(true);

    try {
      // AuthContext owns the Flask session cookie and CSRF token.
      const loggedInUser = await login({
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });
      navigate(destinationFor(loggedInUser, requestedLocation), { replace: true });
    } catch (authErrorResult) {
      const data = authErrorResult?.data || {};
      const code = authErrorResult?.code || data.code;
      const accountStatus = String(data.account_status || '').toLowerCase();

      if (code === 'ACCOUNT_PENDING_APPROVAL' || accountStatus === 'pending') {
        setInfo(
          data.message ||
            'Your registration is awaiting Manager / Team Leader approval. Please allow up to 24 hours for review.'
        );
      } else if (code === 'ACCOUNT_DECLINED' || accountStatus === 'declined') {
        setError(
          data.message ||
            'Your registration was declined. Please contact your Manager or Team Leader.'
        );
      } else if (code === 'ACCOUNT_INACTIVE' || (accountStatus && accountStatus !== 'active')) {
        setError(
          data.message ||
            'This account is inactive. Please contact your Manager or Team Leader.'
        );
      } else if (authErrorResult?.networkError) {
        setError('Unable to reach the authentication server. Please try again.');
      } else {
        setError(authErrorResult?.message || 'Invalid email or password.');
      }
    } finally {
      setLoading(false);
    }
  };

  const displayedError = error || (!info && !dismissSessionMessage ? authError : '');
  const busy = loading || isAuthLoading;

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <p className="eyebrow">Jungle House</p>
        <h1>Welcome Back</h1>
        <p className="muted">
          Sign in with your registered account to access the training assistant.
        </p>

        <form onSubmit={handleCredentialsSubmit} className="form-stack">
          <label>
            Email
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              placeholder="Enter your email"
              autoComplete="username"
              disabled={busy}
              required
            />
          </label>

          <label>
            <div className="row-between">
              <span>Password</span>
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="auth-inline-action"
                disabled={busy}
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
              autoComplete="current-password"
              disabled={busy}
              required
            />
          </label>

          {info ? <p className="muted" role="status">{info}</p> : null}
          {displayedError ? <p className="error-text" role="alert">{displayedError}</p> : null}

          <button className="primary-btn" type="submit" disabled={busy}>
            {loading ? 'Signing in...' : isAuthLoading ? 'Checking session...' : 'Login'}
          </button>

          <div className="row-between wrap-gap top-gap">
            <Link to="/register" className="text-link">Register new account</Link>
            <Link to="/forgot-password" className="text-link">Forgot password?</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

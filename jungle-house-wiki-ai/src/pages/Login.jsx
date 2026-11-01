import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/AuthSecurity.css';

export default function Login() {
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState(null);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  // AuthContext signs in through Flask and verifies the cookie with /auth/me.
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const requestedLocation = location.state?.from;


  useEffect(() => {
    if (!cooldownUntil) {
      setCooldownSeconds(0);
      return undefined;
    }

    const updateCooldown = () => {
      const remaining = Math.max(
        0,
        Math.ceil((cooldownUntil - Date.now()) / 1000)
      );

      setCooldownSeconds(remaining);

      if (remaining <= 0) {
        setCooldownUntil(null);
      }
    };

    updateCooldown();
    const timerId = window.setInterval(updateCooldown, 1000);

    return () => window.clearInterval(timerId);
  }, [cooldownUntil]);

  const formatCooldown = (seconds) => {
    const safeSeconds = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safeSeconds / 60);
    const remainingSeconds = safeSeconds % 60;

    return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
  };

  const loginLocked = cooldownSeconds > 0;

  const destinationFor = () => {
    // Preserve the user's original protected-page destination, including its
    // search/hash, but never navigate to an external URL or back to /login.
    const pathname = requestedLocation?.pathname;
    if (
      typeof pathname === 'string' &&
      pathname.startsWith('/') &&
      !pathname.startsWith('//') &&
      pathname !== '/login'
    ) {
      return `${pathname}${requestedLocation.search || ''}${requestedLocation.hash || ''}`;
    }

    // Staff, Team Leaders and Managers/Admin share the same workspace home.
    // Management links and access remain controlled by StaffLayout, RoleRoute and the backend.
    return '/chat';
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
    setError('');
    setInfo('');
  };

  const handleCredentialsSubmit = async (event) => {
    event.preventDefault();
    if (loading || loginLocked) return;

    setLoading(true);
    setError('');
    setInfo('');

    try {
      // Approval directly changes the backend account to active; there is no
      // activation key or second login stage.
      await login({
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });
      navigate(destinationFor(), { replace: true });
    } catch (authError) {
      const data = authError?.data || {};
      const code = authError?.code || data.code;

      if (code === 'LOGIN_RATE_LIMITED' || authError?.status === 429) {
        // Prefer the real server cooldown. The 15-minute fallback only protects
        // the UX if a proxy/browser hides the Retry-After response header.
        const retryAfterSeconds = Math.max(
          1,
          Number(authError?.retryAfterSeconds) || 15 * 60
        );

        setCooldownUntil(Date.now() + retryAfterSeconds * 1000);
        setCooldownSeconds(retryAfterSeconds);
        setError('');
        setInfo('');
      } else if (code === 'ACCOUNT_PENDING_APPROVAL' || data.account_status === 'pending') {
        setInfo(
          data.message ||
            'Your registration is awaiting Manager / Team Leader approval. Please allow up to 24 hours.'
        );
      } else if (code === 'ACCOUNT_DECLINED' || data.account_status === 'declined') {
        setError(
          data.message ||
            'Your registration was declined. Please contact your Manager or Team Leader.'
        );
      } else if (code === 'ACCOUNT_INACTIVE' || data.account_status === 'inactive') {
        setError(
          data.message ||
            'This account is inactive. Please contact a Manager or Team Leader.'
        );
      } else if (authError?.networkError) {
        setError('Unable to reach the authentication server. Please try again.');
      } else {
        // Includes invalid credentials, expired/invalid sessions and CSRF errors.
        // AuthContext supplies the backend message when one is available.
        setError(authError?.message || 'Unable to sign in. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

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
              required
            />
          </label>

          <label>
            <div className="row-between">
              <span>Password</span>
              <button
                type="button"
                onClick={() => setShowPassword((previous) => !previous)}
                className="auth-inline-action"
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
              required
            />
          </label>

          {info ? <p className="muted" role="status">{info}</p> : null}

          {loginLocked ? (
            <div className="auth-lockout-card" role="alert" aria-live="polite">
              <span className="auth-lockout-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <circle cx="12" cy="12" r="8.25" />
                  <path d="M12 7.75v4.6l3.15 1.85" />
                </svg>
              </span>

              <span className="auth-lockout-copy">
                <strong>Login temporarily locked</strong>
                <span>Too many failed attempts. Try again when the timer ends.</span>
              </span>

              <span
                className="auth-lockout-timer"
                aria-label={`Try again in ${formatCooldown(cooldownSeconds)}`}
              >
                {formatCooldown(cooldownSeconds)}
              </span>
            </div>
          ) : null}

          {error ? <p className="error-text" role="alert">{error}</p> : null}

          <button
            className="primary-btn auth-login-submit"
            type="submit"
            disabled={loading || loginLocked}
          >
            {loading
              ? 'Signing in...'
              : loginLocked
                ? `Login locked · ${formatCooldown(cooldownSeconds)}`
                : 'Login'}
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

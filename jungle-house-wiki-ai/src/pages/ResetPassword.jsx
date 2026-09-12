import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import '../styles/AuthSecurity.css';

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [form, setForm] = useState({ new_password: '', confirm_password: '' });
  const [validating, setValidating] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showPasswords, setShowPasswords] = useState(false);

  const checks = useMemo(
    () => ({
      length: form.new_password.length >= 8,
      uppercase: /[A-Z]/.test(form.new_password),
      number: /\d/.test(form.new_password),
      match:
        Boolean(form.confirm_password) &&
        form.new_password === form.confirm_password,
    }),
    [form.new_password, form.confirm_password]
  );

  useEffect(() => {
    let cancelled = false;

    const validateToken = async () => {
      if (!token) {
        if (!cancelled) {
          setTokenValid(false);
          setError('Password reset link is invalid or expired.');
          setValidating(false);
        }
        return;
      }

      try {
        await api.get('/auth/reset-password/validate', { params: { token } });
        if (!cancelled) setTokenValid(true);
      } catch (requestError) {
        if (!cancelled) {
          setTokenValid(false);
          setError(
            requestError.response?.data?.message ||
              'Password reset link is invalid or expired.'
          );
        }
      } finally {
        if (!cancelled) setValidating(false);
      }
    };

    validateToken();
    return () => { cancelled = true; };
  }, [token]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (!checks.length || !checks.uppercase || !checks.number) {
      setError('Password must be at least 8 characters and include an uppercase letter and a number.');
      return;
    }

    if (!checks.match) {
      setError('Passwords do not match.');
      return;
    }

    try {
      setLoading(true);
      const response = await api.post('/auth/reset-password', {
        token,
        new_password: form.new_password,
        confirm_password: form.confirm_password,
      });
      setSuccess(response.data?.message || 'Password updated successfully.');
      setTokenValid(false);
      setTimeout(() => navigate('/login', { replace: true }), 1600);
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to reset the password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <p className="eyebrow">Jungle House</p>
        <h1>Reset Password</h1>

        {validating ? (
          <p className="muted">Checking your reset link...</p>
        ) : success ? (
          <>
            <p className="auth-success-message">{success}</p>
            <p className="muted">Returning to sign in...</p>
          </>
        ) : tokenValid ? (
          <form onSubmit={handleSubmit} className="form-stack">
            <p className="muted">Create a new password for your account.</p>

            <div className="row-between">
              <strong>New password</strong>
              <button
                type="button"
                className="auth-inline-action"
                onClick={() => setShowPasswords((previous) => !previous)}
              >
                {showPasswords ? 'Hide' : 'Show'}
              </button>
            </div>

            <input
              type={showPasswords ? 'text' : 'password'}
              value={form.new_password}
              onChange={(event) => setForm((previous) => ({ ...previous, new_password: event.target.value }))}
              placeholder="New password"
              autoComplete="new-password"
              required
            />

            <input
              type={showPasswords ? 'text' : 'password'}
              value={form.confirm_password}
              onChange={(event) => setForm((previous) => ({ ...previous, confirm_password: event.target.value }))}
              placeholder="Confirm new password"
              autoComplete="new-password"
              required
            />

            <div className="auth-password-checks">
              <span className={checks.length ? 'passed' : ''}>{checks.length ? '✓' : '○'} 8+ characters</span>
              <span className={checks.uppercase ? 'passed' : ''}>{checks.uppercase ? '✓' : '○'} Uppercase</span>
              <span className={checks.number ? 'passed' : ''}>{checks.number ? '✓' : '○'} Number</span>
              <span className={checks.match ? 'passed' : ''}>{checks.match ? '✓' : '○'} Passwords match</span>
            </div>

            {error ? <p className="error-text">{error}</p> : null}

            <button className="primary-btn" type="submit" disabled={loading}>
              {loading ? 'Updating...' : 'Update Password'}
            </button>
          </form>
        ) : (
          <>
            {error ? <p className="error-text">{error}</p> : null}
            <Link to="/forgot-password" className="primary-btn auth-link-button">
              Request New Reset Link
            </Link>
          </>
        )}

        <div className="auth-footer-row top-gap">
          <Link to="/login" className="text-link">Back to Sign In</Link>
        </div>
      </div>
    </div>
  );
}

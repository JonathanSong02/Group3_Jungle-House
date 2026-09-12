import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import '../styles/AuthSecurity.css';

export default function Login() {
  const [form, setForm] = useState({ email: '', password: '' });
  const [registrationKey, setRegistrationKey] = useState('');
  const [stage, setStage] = useState('credentials');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [attemptsRemaining, setAttemptsRemaining] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [registrationCancelled, setRegistrationCancelled] = useState(false);

  // IMPORTANT: normal login goes through the existing AuthContext.login()
  // just like the project did before the registration-key feature was added.
  const { login, updateUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const requestedPath = location.state?.from?.pathname || '';

  const destinationFor = (loggedInUser) => {
    if (requestedPath) return requestedPath;

    const role = String(loggedInUser?.role || '')
      .toLowerCase()
      .replace(/[\s_-]/g, '');

    return role === 'manager' ? '/admin/dashboard' : '/dashboard';
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setError('');
  };

  const handleCredentialsSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    setInfo('');
    setRegistrationCancelled(false);

    const credentials = {
      email: form.email.trim().toLowerCase(),
      password: form.password,
    };

    try {
      // Preserve the original, already-working project login path.
      const loggedInUser = await login(credentials);
      navigate(destinationFor(loggedInUser), { replace: true });
    } catch (authError) {
      const data = authError?.data || {};
      const code = authError?.code || data?.code;

      if (code === 'REGISTRATION_KEY_REQUIRED') {
        setStage('activation');
        setAttemptsRemaining(data.attempts_remaining ?? 3);
        setInfo(
          data.message ||
            'Your account was approved. Enter the one-time registration key sent to your email.'
        );
        return;
      }

      if (code === 'ACCOUNT_PENDING_APPROVAL') {
        setInfo(data.message || 'Your registration is still awaiting approval.');
        return;
      }

      if (code === 'ACCOUNT_DECLINED') {
        setError(
          data.message ||
            'This registration is no longer active. Please register again if required.'
        );
        return;
      }

      if (code === 'ACCOUNT_INACTIVE') {
        setError(
          data.message ||
            'This account is inactive. Please contact a Manager or Team Leader.'
        );
        return;
      }

      if (authError?.networkError) {
        setError('Unable to reach the authentication server. Please try again.');
        return;
      }

      setError(authError?.message || 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  const handleActivationSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/activate-registration-key', {
        email: form.email.trim().toLowerCase(),
        password: form.password,
        registration_key: registrationKey.trim().toLowerCase(),
      });

      const activatedUser = response.data?.user;

      if (!activatedUser) {
        throw new Error('Account was activated, but user details were not returned.');
      }

      updateUser(activatedUser);
      navigate(destinationFor(activatedUser), { replace: true });
    } catch (requestError) {
      const data = requestError.response?.data || {};

      if (typeof data.attempts_remaining === 'number') {
        setAttemptsRemaining(data.attempts_remaining);
      }

      if (data.code === 'ACTIVATION_KEY_LOCKED') {
        setRegistrationCancelled(true);
        setError(
          data.message ||
            'Registration cancelled after 3 incorrect key attempts. Please register again.'
        );
        return;
      }

      setError(data.message || requestError.message || 'Unable to verify the registration key.');
    } finally {
      setLoading(false);
    }
  };

  const resendActivationKey = async () => {
    setLoading(true);
    setError('');
    setInfo('');

    try {
      const response = await api.post('/auth/resend-activation-key', {
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });
      setInfo(response.data?.message || 'The activation key has been resent to your email.');
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to resend the activation key.');
    } finally {
      setLoading(false);
    }
  };

  const backToCredentials = () => {
    setStage('credentials');
    setRegistrationKey('');
    setError('');
    setInfo('');
    setAttemptsRemaining(null);
    setRegistrationCancelled(false);
  };

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <p className="eyebrow">Jungle House</p>
        <h1>{stage === 'activation' ? 'Activate Your Account' : 'Welcome Back'}</h1>
        <p className="muted">
          {stage === 'activation'
            ? 'Your registration was approved. Enter the one-time key sent to your registered email.'
            : 'Sign in with your registered account to access the training assistant.'}
        </p>

        {stage === 'credentials' ? (
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
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="auth-inline-action"
                  tabIndex="-1"
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

            {info ? <p className="muted">{info}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}

            <button className="primary-btn" type="submit" disabled={loading}>
              {loading ? 'Signing in...' : 'Login'}
            </button>

            <div className="row-between wrap-gap top-gap">
              <Link to="/register" className="text-link">Register new account</Link>
              <Link to="/forgot-password" className="text-link">Forgot password?</Link>
            </div>
          </form>
        ) : (
          <form onSubmit={handleActivationSubmit} className="form-stack">
            <div className="card-like" style={{ padding: '12px' }}>
              <strong>{form.email.trim().toLowerCase()}</strong>
              <p className="muted" style={{ marginBottom: 0 }}>
                Approved account • activation required
              </p>
            </div>

            <label>
              One-time registration key
              <input
                type="text"
                value={registrationKey}
                onChange={(event) => {
                  setRegistrationKey(event.target.value);
                  setError('');
                }}
                placeholder="Enter the 10-character key"
                autoComplete="one-time-code"
                maxLength={10}
                disabled={registrationCancelled}
                required
              />
            </label>

            {!registrationCancelled && attemptsRemaining !== null ? (
              <p className="muted">
                {attemptsRemaining} activation attempt{attemptsRemaining === 1 ? '' : 's'} remaining.
              </p>
            ) : null}

            {info ? <p className="muted">{info}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}

            {!registrationCancelled ? (
              <>
                <button className="primary-btn" type="submit" disabled={loading}>
                  {loading ? 'Verifying...' : 'Verify Key & Enter System'}
                </button>
                <button
                  className="secondary-btn"
                  type="button"
                  disabled={loading}
                  onClick={resendActivationKey}
                >
                  Resend Key to Email
                </button>
              </>
            ) : (
              <Link
                to="/register"
                className="primary-btn"
                style={{ textAlign: 'center', textDecoration: 'none' }}
              >
                Register Again
              </Link>
            )}

            <button className="text-link" type="button" onClick={backToCredentials}>
              Back to Sign In
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

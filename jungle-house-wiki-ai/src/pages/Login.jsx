import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import LanguageSelector from '../i18n/LanguageSelector';
import { translateServerMessage } from '../i18n/serverMessages';
import { formatCooldown, isLockedFor } from '../utils/loginCooldown';
import '../styles/AuthSecurity.css';

export default function Login() {
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState(null);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  // The server locks one account on this device, so remember which email it was.
  const [lockedEmail, setLockedEmail] = useState('');

  // AuthContext signs in through Flask and verifies the cookie with /auth/me.
  const { login } = useAuth();
  const { t } = useLanguage();
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

  // Locked only while the email typed is the one the server locked on this
  // device. Another account can still be used here; the server decides anyway.
  const loginLocked = isLockedFor(lockedEmail, form.email, cooldownSeconds);
  const cooldownText = formatCooldown(cooldownSeconds);

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

    const submittedEmail = form.email.trim().toLowerCase();

    try {
      // Approval directly changes the backend account to active; there is no
      // activation key or second login stage.
      await login({
        email: submittedEmail,
        password: form.password,
      });
      navigate(destinationFor(), { replace: true });
    } catch (authError) {
      const data = authError?.data || {};
      const code = authError?.code || data.code;

      if (code === 'LOGIN_RATE_LIMITED' || authError?.status === 429) {
        // The remaining time comes from the server (response body, then the
        // Retry-After header). The 15-minute fallback is only used if a proxy
        // or browser hides both; the server still enforces the real time.
        const retryAfterSeconds = Math.max(
          1,
          Number(authError?.retryAfterSeconds) || 15 * 60
        );

        setLockedEmail(submittedEmail);
        setCooldownUntil(Date.now() + retryAfterSeconds * 1000);
        setCooldownSeconds(retryAfterSeconds);
        setError('');
        setInfo('');
      } else if (code === 'INVALID_CREDENTIALS') {
        // Same text for a wrong password and for an email that is not registered.
        setError(t('login.error.invalid'));
      } else if (code === 'ACCOUNT_PENDING_APPROVAL' || data.account_status === 'pending') {
        setInfo(translateServerMessage(t, data.message) || t('auth.login.pending'));
      } else if (code === 'ACCOUNT_DECLINED' || data.account_status === 'declined') {
        setError(translateServerMessage(t, data.message) || t('auth.login.declined'));
      } else if (code === 'ACCOUNT_INACTIVE' || data.account_status === 'inactive') {
        setError(translateServerMessage(t, data.message) || t('auth.login.inactive'));
      } else if (authError?.networkError) {
        setError(t('auth.unreachable'));
      } else {
        // Includes invalid credentials, expired/invalid sessions and CSRF errors.
        // AuthContext supplies the backend message when one is available.
        setError(translateServerMessage(t, authError?.message) || t('auth.login.failed'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <LanguageSelector className="jh-lang-auth" placement="down" />
        <p className="eyebrow">Jungle House</p>
        <h1>{t('auth.login.title')}</h1>
        <p className="muted">
          {t('auth.login.subtitle')}
        </p>

        <form onSubmit={handleCredentialsSubmit} className="form-stack">
          <label>
            {t('auth.email')}
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              placeholder={t('auth.login.emailPlaceholder')}
              autoComplete="username"
              required
            />
          </label>

          <label>
            <div className="row-between">
              <span>{t('auth.password')}</span>
              <button
                type="button"
                onClick={() => setShowPassword((previous) => !previous)}
                className="auth-inline-action"
              >
                {showPassword ? t('auth.hide') : t('auth.show')}
              </button>
            </div>
            <input
              name="password"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              onChange={handleChange}
              placeholder={t('auth.login.passwordPlaceholder')}
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
                <strong>{t('login.lock.title')}</strong>
                <span>{t('login.lock.text', { time: cooldownText })}</span>
                <span>{t('login.lock.hint')}</span>
              </span>

              <span
                className="auth-lockout-timer"
                aria-label={t('login.lock.timer', { time: cooldownText })}
              >
                {cooldownText}
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
              ? t('auth.login.signingIn')
              : loginLocked
                ? t('login.lock.button', { time: cooldownText })
                : t('auth.login.submit')}
          </button>

          <div className="row-between wrap-gap top-gap">
            <Link to="/register" className="text-link">{t('auth.login.register')}</Link>
            <Link to="/forgot-password" className="text-link">{t('auth.login.forgot')}</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

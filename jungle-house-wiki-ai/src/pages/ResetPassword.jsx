import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';
import LanguageSelector from '../i18n/LanguageSelector';
import { translateServerMessage } from '../i18n/serverMessages';
import '../styles/AuthSecurity.css';

export default function ResetPassword() {
  const navigate = useNavigate();
  const { t } = useLanguage();
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
      setError(t('auth.passwordRule'));
      return;
    }

    if (!checks.match) {
      setError(t('auth.passwordsNoMatch'));
      return;
    }

    try {
      setLoading(true);
      const response = await api.post('/auth/reset-password', {
        token,
        new_password: form.new_password,
        confirm_password: form.confirm_password,
      });
      setSuccess(translateServerMessage(t, response.data?.message) || t('auth.reset.updated'));
      setTokenValid(false);
      setTimeout(() => navigate('/login', { replace: true }), 1600);
    } catch (requestError) {
      const status = requestError.response?.status;
      setError(translateServerMessage(t, requestError.response?.data?.message) || t('auth.reset.failed'));

      // If the server says the token is invalid, expired, already used, or
      // no longer eligible, stop showing the password form and offer a fresh
      // reset link instead. Transient server errors keep the form available.
      if ([400, 403, 409].includes(status)) {
        setTokenValid(false);
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
        <h1>{t('auth.reset.title')}</h1>

        {validating ? (
          <p className="muted">{t('auth.reset.checking')}</p>
        ) : success ? (
          <>
            <p className="auth-success-message">{success}</p>
            <p className="muted">{t('auth.reset.returning')}</p>
          </>
        ) : tokenValid ? (
          <form onSubmit={handleSubmit} className="form-stack">
            <p className="muted">{t('auth.reset.intro')}</p>

            <div className="row-between">
              <strong>{t('auth.reset.newPassword')}</strong>
              <button
                type="button"
                className="auth-inline-action"
                onClick={() => setShowPasswords((previous) => !previous)}
              >
                {showPasswords ? t('auth.hide') : t('auth.show')}
              </button>
            </div>

            <input
              type={showPasswords ? 'text' : 'password'}
              value={form.new_password}
              onChange={(event) => setForm((previous) => ({ ...previous, new_password: event.target.value }))}
              placeholder={t('auth.reset.newPassword')}
              autoComplete="new-password"
              required
            />

            <input
              type={showPasswords ? 'text' : 'password'}
              value={form.confirm_password}
              onChange={(event) => setForm((previous) => ({ ...previous, confirm_password: event.target.value }))}
              placeholder={t('auth.reset.confirmPassword')}
              autoComplete="new-password"
              required
            />

            <div className="auth-password-checks">
              <span className={checks.length ? 'passed' : ''}>{checks.length ? '✓' : '○'} {t('profile.pw.chars')}</span>
              <span className={checks.uppercase ? 'passed' : ''}>{checks.uppercase ? '✓' : '○'} {t('profile.pw.upper')}</span>
              <span className={checks.number ? 'passed' : ''}>{checks.number ? '✓' : '○'} {t('profile.pw.number')}</span>
              <span className={checks.match ? 'passed' : ''}>{checks.match ? '✓' : '○'} {t('profile.pw.match')}</span>
            </div>

            {error ? <p className="error-text">{translateServerMessage(t, error)}</p> : null}

            <button className="primary-btn" type="submit" disabled={loading}>
              {loading ? t('auth.reset.updating') : t('profile.pw.update')}
            </button>
          </form>
        ) : (
          <div className="reset-expired-state">
            <div className="reset-status-card reset-status-error">
              <div className="reset-status-icon" aria-hidden="true">!</div>

              <div className="reset-status-content">
                <strong>{t('auth.reset.invalidTitle')}</strong>
                <p>
                  {translateServerMessage(t, error) || t('auth.reset.invalidDefault')}
                </p>
              </div>
            </div>

            <p className="reset-help-text">
              {t('auth.reset.requestHelp')}
            </p>

            <div className="reset-action-stack">
              <Link
                to="/forgot-password"
                className="primary-btn auth-link-button reset-primary-action"
              >
                {t('auth.reset.requestNew')}
              </Link>

              <Link to="/login" className="reset-secondary-action">
                {t('auth.backToSignIn')}
              </Link>
            </div>
          </div>
        )}

        {validating || success || tokenValid ? (
          <div className="auth-footer-row top-gap">
            <Link to="/login" className="text-link">{t('auth.backToSignIn')}</Link>
          </div>
        ) : null}
      </div>
    </div>
  );
}

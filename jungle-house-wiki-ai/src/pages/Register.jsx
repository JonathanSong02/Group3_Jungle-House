import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';
import LanguageSelector from '../i18n/LanguageSelector';
import { translateServerMessage } from '../i18n/serverMessages';
import '../styles/AuthSecurity.css';

export default function Register() {
  const navigate = useNavigate();
  const { t } = useLanguage();

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    if (error) setError('');
  };

  const passwordChecks = useMemo(
    () => ({
      length: form.password.length >= 8,
      uppercase: /[A-Z]/.test(form.password),
      number: /\d/.test(form.password),
      match:
        Boolean(form.confirm_password) &&
        form.password === form.confirm_password,
    }),
    [form.password, form.confirm_password]
  );

  const passwordValid =
    passwordChecks.length &&
    passwordChecks.uppercase &&
    passwordChecks.number;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (form.password !== form.confirm_password) {
      setError(t('auth.passwordsNoMatch'));
      return;
    }

    if (!passwordValid) {
      setError(t('auth.passwordRule'));
      return;
    }

    try {
      setLoading(true);

      const response = await api.post('/auth/register', {
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        confirm_password: form.confirm_password,
      });

      // Show success only for the backend's confirmed pending registration.
      if (response.data?.account_status !== 'pending') {
        throw new Error(t('auth.register.unconfirmed'));
      }

      setShowSuccessModal(true);
    } catch (requestError) {
      setError(
        translateServerMessage(t, requestError.response?.data?.message || requestError.message) ||
          t('auth.register.failed')
      );
    } finally {
      setLoading(false);
    }
  };

  const goToLogin = () => {
    setShowSuccessModal(false);
    navigate('/login');
  };

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <LanguageSelector className="jh-lang-auth" placement="down" />
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">
            JH
          </span>
          <div>
            <p className="eyebrow">Jungle House AI Wiki</p>
            <span>{t('auth.register.subtitle')}</span>
          </div>
        </div>

        <div className="auth-heading">
          <h1>{t('auth.register.title')}</h1>
          <p>
            {t('auth.register.intro')}
          </p>
        </div>

        <div className="auth-registration-flow" aria-label={t('auth.register.steps')}>
          <span className="current">{t('auth.register.step1')}</span>
          <span>{t('auth.register.step2')}</span>
          <span>{t('auth.register.step3')}</span>
        </div>

        <form onSubmit={handleSubmit} className="form-stack auth-form">
          <label>
            {t('auth.register.fullName')}
            <input
              type="text"
              name="full_name"
              placeholder={t('auth.register.fullNamePlaceholder')}
              value={form.full_name}
              onChange={handleChange}
              autoComplete="name"
              required
            />
          </label>

          <label>
            {t('auth.register.email')}
            <input
              type="email"
              name="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              autoComplete="email"
              required
            />
          </label>

          <div className="row-between">
            <strong className="auth-field-heading">{t('auth.password')}</strong>
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
            name="password"
            placeholder={t('auth.register.createPassword')}
            value={form.password}
            onChange={handleChange}
            autoComplete="new-password"
            required
          />

          <input
            type={showPasswords ? 'text' : 'password'}
            name="confirm_password"
            placeholder={t('auth.register.confirmPassword')}
            value={form.confirm_password}
            onChange={handleChange}
            autoComplete="new-password"
            required
          />

          <div className="auth-password-checks">
            <span className={passwordChecks.length ? 'passed' : ''}>
              {passwordChecks.length ? '✓' : '○'} {t('profile.pw.chars')}
            </span>
            <span className={passwordChecks.uppercase ? 'passed' : ''}>
              {passwordChecks.uppercase ? '✓' : '○'} {t('profile.pw.upper')}
            </span>
            <span className={passwordChecks.number ? 'passed' : ''}>
              {passwordChecks.number ? '✓' : '○'} {t('profile.pw.number')}
            </span>
            <span className={passwordChecks.match ? 'passed' : ''}>
              {passwordChecks.match ? '✓' : '○'} {t('profile.pw.match')}
            </span>
          </div>

          {error ? (
            <p className="auth-error-message" role="alert">
              {error}
            </p>
          ) : null}

          <button
            className="primary-btn auth-primary-action"
            type="submit"
            disabled={loading}
          >
            {loading ? t('auth.register.submitting') : t('auth.register.submit')}
          </button>

          <div className="auth-footer-row">
            <span>{t('auth.register.already')}</span>
            <Link to="/login" className="text-link">
              {t('auth.backToSignIn')}
            </Link>
          </div>
        </form>
      </div>

      {showSuccessModal ? (
        <div className="auth-modal-overlay" role="presentation">
          <div
            className="auth-success-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="registration-success-title"
          >
            <span className="auth-success-mark" aria-hidden="true">
              ✓
            </span>

            <p className="eyebrow">{t('auth.register.submittedEyebrow')}</p>
            <h2 id="registration-success-title">{t('auth.register.received')}</h2>

            <p>
              {t('auth.register.successText')}
            </p>

            <div className="auth-success-steps">
              <div className="done">
                <strong>1</strong>
                <span>{t('auth.register.submittedEyebrow')}</span>
              </div>
              <div>
                <strong>2</strong>
                <span>{t('auth.register.reviewStep')}</span>
              </div>
              <div>
                <strong>3</strong>
                <span>{t('auth.register.signInStep')}</span>
              </div>
            </div>

            <button
              type="button"
              className="primary-btn auth-primary-action"
              onClick={goToLogin}
            >
              {t('auth.register.goToSignIn')}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

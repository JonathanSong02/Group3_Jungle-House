import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';
import LanguageSelector from '../i18n/LanguageSelector';
import { translateServerMessage } from '../i18n/serverMessages';
import '../styles/AuthSecurity.css';

export default function ForgotPassword() {
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');

    try {
      setLoading(true);
      const response = await api.post('/auth/forgot-password', {
        email: email.trim().toLowerCase(),
      });
      setMessage(translateServerMessage(t, response.data?.message) || t('auth.forgot.generic'));
    } catch (requestError) {
      const data = requestError.response?.data || {};

      if (data.code === 'PASSWORD_RECOVERY_UNAVAILABLE') {
        setError(translateServerMessage(t, data.message) || t('auth.forgot.notConfigured'));
      } else {
        // Keep the response generic so the page does not reveal account existence.
        console.error('FORGOT PASSWORD: Request failed.');
        setMessage(t('auth.forgot.generic'));
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
        <h1>{t('auth.forgot.title')}</h1>
        <p className="muted">
          {t('auth.forgot.intro')}
        </p>

        <form onSubmit={handleSubmit} className="form-stack">
          <label>
            {t('auth.email')}
            <input
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setError('');
                setMessage('');
              }}
              placeholder={t('auth.forgot.placeholder')}
              autoComplete="email"
              required
            />
          </label>

          {message ? <p className="auth-success-message">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? t('auth.forgot.sending') : t('auth.forgot.send')}
          </button>

          <div className="auth-footer-row">
            <Link to="/login" className="text-link">{t('auth.backToSignIn')}</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

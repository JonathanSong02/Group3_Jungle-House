import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import '../styles/AuthSecurity.css';

export default function ForgotPassword() {
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
      setMessage(
        response.data?.message ||
          'If this email belongs to an eligible account, a password reset link will be sent shortly.'
      );
    } catch {
      // Keep the response generic so the page does not reveal account existence.
      console.error('FORGOT PASSWORD: Request failed.');
      setMessage(
        'If this email belongs to an eligible account, a password reset link will be sent shortly.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <p className="eyebrow">Jungle House</p>
        <h1>Forgot Password</h1>
        <p className="muted">
          Enter your registered email. If the account is eligible, the system
          will email you a secure password-reset link.
        </p>

        <form onSubmit={handleSubmit} className="form-stack">
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setError('');
                setMessage('');
              }}
              placeholder="Enter your registered email"
              autoComplete="email"
              required
            />
          </label>

          {message ? <p className="auth-success-message">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Sending...' : 'Send Reset Link'}
          </button>

          <div className="auth-footer-row">
            <Link to="/login" className="text-link">Back to Sign In</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

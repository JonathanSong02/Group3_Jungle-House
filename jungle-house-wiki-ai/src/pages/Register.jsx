import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function Register() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showPendingModal, setShowPendingModal] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const togglePasswordVisibility = () => {
    setShowPassword((prev) => !prev);
  };

  const validatePassword = (password) => {
    const minLength = 8;
    const hasNumber = /\d/.test(password);
    const hasUpper = /[A-Z]/.test(password);

    return password.length >= minLength && hasNumber && hasUpper;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (form.password !== form.confirm_password) {
      setError('Passwords do not match.');
      return;
    }

    if (!validatePassword(form.password)) {
      setError(
        'Password must be at least 8 characters, include a number, and an uppercase letter.'
      );
      return;
    }

    try {
      setLoading(true);

      const payload = {
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        confirm_password: form.confirm_password,

        // Security flow:
        // New users register with an approved company email domain first.
        // Manager / Team Lead will approve or decline the account later.
        role: 'staff',
      };

      const response = await api.post('/auth/register', payload);

      setSuccess(
        response.data.message ||
          'Registration submitted. Please check your email for the verification link.'
      );

      setShowPendingModal(true);
    } catch (err) {
      setError(err.response?.data?.message || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  const goToLogin = () => {
    setShowPendingModal(false);
    navigate('/login');
  };

  return (
    <div className="login-page">
      <div className="login-card card-like">
        <p className="eyebrow">Jungle House</p>
        <h1>Create Account</h1>

        <p className="muted">
          Register using your approved staff email address. A verification link
          will be sent to your email first. After verification, your account
          will be reviewed by a manager or team lead within 24 hours.
        </p>

        <form onSubmit={handleSubmit} className="form-stack">
          <input
            type="text"
            name="full_name"
            placeholder="Full name"
            value={form.full_name}
            onChange={handleChange}
            required
          />

          <input
            type="email"
            name="email"
            placeholder="Staff email address"
            value={form.email}
            onChange={handleChange}
            autoComplete="username"
            required
          />

          <div
            style={{
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <div
              className="row-between"
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                marginBottom: '-0.5rem',
              }}
            >
              <button
                type="button"
                onClick={togglePasswordVisibility}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  color: '#555',
                }}
                tabIndex="-1"
              >
                {showPassword ? 'Hide Passwords' : 'Show Passwords'}
              </button>
            </div>

            <input
              type={showPassword ? 'text' : 'password'}
              name="password"
              placeholder="Password"
              value={form.password}
              onChange={handleChange}
              autoComplete="new-password"
              required
            />

            <input
              type={showPassword ? 'text' : 'password'}
              name="confirm_password"
              placeholder="Confirm password"
              value={form.confirm_password}
              onChange={handleChange}
              autoComplete="new-password"
              required
            />
          </div>

          {error ? <p className="error-text">{error}</p> : null}
          {success ? <p style={{ color: '#2f6b3d' }}>{success}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Submitting...' : 'Register'}
          </button>

          <div style={{ marginTop: '1rem', textAlign: 'center' }}>
            <Link to="/login" className="text-link">
              Back to Login
            </Link>
          </div>
        </form>
      </div>

      {showPendingModal ? (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1rem',
          }}
        >
          <div
            className="card-like"
            style={{
              maxWidth: '480px',
              width: '100%',
              textAlign: 'center',
              padding: '2rem',
            }}
          >
            <p className="eyebrow">Account Submitted</p>

            <h2 style={{ marginBottom: '0.75rem' }}>
              Check your email first
            </h2>

            <p className="muted" style={{ marginBottom: '1.5rem' }}>
              Your account registration has been received. Please click the
              verification link sent to your registered email. After your email
              is verified, a manager or team lead will approve or decline your
              account within 24 hours, and you will be notified by email.
            </p>

            <button type="button" className="primary-btn" onClick={goToLogin}>
              Go to Login
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

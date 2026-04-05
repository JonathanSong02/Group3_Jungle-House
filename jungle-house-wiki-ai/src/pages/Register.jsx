import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function Register() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    role: 'staff',
    password: '',
    confirm_password: '',
    access_key: '',
  });

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (form.password !== form.confirm_password) {
      setError('Passwords do not match.');
      return;
    }

    try {
      setLoading(true);

      const response = await api.post('/auth/register', form);

      setSuccess(response.data.message || 'Registration successful.');

      setTimeout(() => {
        navigate('/login');
      }, 1500);
    } catch (err) {
      setError(err.response?.data?.message || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card-like">
        <p className="eyebrow">Jungle House</p>
        <h1>Create Account</h1>
        <p className="muted">
          New staff and team leads need a registration key from the manager.
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
            placeholder="Email"
            value={form.email}
            onChange={handleChange}
            required
          />

          <select
            name="role"
            value={form.role}
            onChange={handleChange}
          >
            <option value="staff">Staff</option>
            <option value="teamlead">Team Lead</option>
          </select>

          <input
            type="password"
            name="password"
            placeholder="Password"
            value={form.password}
            onChange={handleChange}
            required
          />

          <input
            type="password"
            name="confirm_password"
            placeholder="Confirm password"
            value={form.confirm_password}
            onChange={handleChange}
            required
          />

          <input
            type="text"
            name="access_key"
            placeholder="Manager registration key"
            value={form.access_key}
            onChange={handleChange}
            required
          />

          {error ? <p className="error-text">{error}</p> : null}
          {success ? <p style={{ color: '#2f6b3d' }}>{success}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Registering...' : 'Register'}
          </button>

          <Link to="/login" className="text-link">
            Back to Login
          </Link>
        </form>
      </div>
    </div>
  );
}
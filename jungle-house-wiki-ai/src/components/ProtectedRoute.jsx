import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, isAuthLoading } = useAuth();
  const location = useLocation();

  // AuthContext verifies the signed Flask session on initial load. Do not
  // redirect or render protected content until that check has finished.
  if (isAuthLoading) {
    return (
      <div role="status" aria-live="polite">
        Checking your session...
      </div>
    );
  }

  // Never use a cached profile as proof of login. AuthContext only supplies
  // a user after the backend confirms an active session.
  if (!user || String(user.status || '').toLowerCase() !== 'active') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children;
}

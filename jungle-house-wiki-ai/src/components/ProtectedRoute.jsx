import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, isLoading, loading } = useAuth();
  const location = useLocation();

  // Wait for Flask to verify the session before deciding whether to redirect.
  // Keep the legacy `loading` alias compatible with existing AuthContext versions.
  if (isLoading ?? loading) {
    return (
      <div role="status" aria-live="polite">
        Checking your session…
      </div>
    );
  }

  // Only an active, server-verified account may render protected pages.
  // The backend remains responsible for enforcing permissions on every API call.
  if (!user || user.id == null || user.status !== 'active') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children;
}

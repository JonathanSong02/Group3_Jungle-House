import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function normaliseRole(role) {
  // Account roles come from Flask; normalise naming, not permissions.
  return String(role || '').trim().toLowerCase().replace(/[\s_-]/g, '');
}

export default function RoleRoute({ allowedRoles, children }) {
  const { user, isLoading, loading } = useAuth();
  const location = useLocation();

  // Refreshing a protected URL must not redirect before /auth/me finishes.
  if (isLoading ?? loading) {
    return (
      <div role="status" aria-live="polite">
        Checking your session…
      </div>
    );
  }

  // A role check does not establish identity: Flask must verify the session.
  if (!user || user.id == null || user.status !== 'active') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const role = normaliseRole(user.role);
  const permittedRoles = Array.isArray(allowedRoles)
    ? allowedRoles.map(normaliseRole)
    : [];

  if (permittedRoles.includes(role)) {
    return children;
  }

  // All recognised roles share the same safe workspace home.
  // Unknown roles go to Profile rather than an inaccessible chat route.
  const destination = ['staff', 'teamlead', 'manager', 'admin'].includes(role)
    ? '/chat'
    : '/profile';

  if (location.pathname === destination) {
    return <div role="alert">You do not have permission to view this page.</div>;
  }

  return <Navigate to={destination} replace />;
}

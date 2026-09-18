import StaffLayout from './StaffLayout';

// All authenticated roles use one workspace shell. Access to individual pages
// remains enforced by App.jsx / RoleRoute and the Flask backend.
export default function Layout() {
  return <StaffLayout />;
}

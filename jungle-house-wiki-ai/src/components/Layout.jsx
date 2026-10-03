import { Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import StaffLayout from './StaffLayout';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function Layout() {
  const { user } = useAuth();
  if (String(user?.role || '').trim().toLowerCase() === 'staff') return <StaffLayout />;
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-area">
        <Topbar />
        <section className="page-content">
          <Outlet />
        </section>
      </main>
    </div>
  );
}

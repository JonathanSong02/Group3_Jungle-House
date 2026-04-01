import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function Layout() {
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

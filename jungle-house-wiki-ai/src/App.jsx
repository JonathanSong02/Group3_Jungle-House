import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import RoleRoute from './components/RoleRoute';
import { useAuth } from './context/AuthContext';

import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import KnowledgeBase from './pages/KnowledgeBase';
import ArticleDetail from './pages/ArticleDetail';
import Escalation from './pages/Escalation';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import QuizList from './pages/QuizList';

import Messages from './pages/Messages';

import AdminDashboard from './pages/admin/AdminDashboard';
import AddArticle from './pages/admin/AddArticle';
import EditArticle from './pages/admin/EditArticle';
import QuizManagement from './pages/admin/QuizManagement';
import ContentManagement from './pages/admin/ContentManagement';
import ReviewManagement from './pages/admin/ReviewManagement';
import UserManagement from './pages/admin/UserManagement';
import AISettings from './pages/admin/AISettings';
import NotionSync from './pages/admin/NotionSync';
import Analytics from './pages/admin/Analytics';
import SecurityMonitoring from './pages/admin/SecurityMonitoring';

import SOPSelection from './pages/SOPSelection';

// Everyone gets the same core workspace. Extra routes remain role-restricted.
const WORKSPACE_ROLES = ['staff', 'teamlead', 'manager', 'admin'];
const MANAGEMENT_ROLES = ['teamlead', 'manager', 'admin'];
const MANAGER_ROLES = ['manager', 'admin'];

function StaffDashboardRedirect() {
  const { user } = useAuth();
  const role = String(user?.role || '').trim().toLowerCase().replace(/[\s_-]/g, '');
  return role === 'staff' ? <Navigate to="/chat" replace /> : <Dashboard />;
}

function HomeRedirect() {
  // A common entry point for Staff, Team Leader and Manager/Admin.
  return <Navigate to="/chat" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />

        <Route
          path="messages"
          element={
            <ProtectedRoute>
              <Messages />
            </ProtectedRoute>
          }
        />

        <Route
          path="dashboard"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <StaffDashboardRedirect />
            </RoleRoute>
          }
        />

        <Route
          path="knowledge"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <KnowledgeBase />
            </RoleRoute>
          }
        />

        <Route
          path="knowledge/:id"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <ArticleDetail />
            </RoleRoute>
          }
        />

        <Route
          path="notifications"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <Notifications />
            </RoleRoute>
          }
        />

        <Route
          path="quiz"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <QuizList />
            </RoleRoute>
          }
        />

        <Route
          path="sop-selection"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <SOPSelection />
            </RoleRoute>
          }
        />

        <Route
          path="chat"
          element={
            <RoleRoute allowedRoles={WORKSPACE_ROLES}>
              <Chat />
            </RoleRoute>
          }
        />

        <Route path="profile" element={<Profile />} />

        <Route
          path="escalation"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <Escalation />
            </RoleRoute>
          }
        />

        <Route
          path="admin/dashboard"
          element={
            <RoleRoute allowedRoles={MANAGER_ROLES}>
              <AdminDashboard />
            </RoleRoute>
          }
        />

        <Route
          path="admin/content"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <ContentManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/content/add"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <AddArticle />
            </RoleRoute>
          }
        />

        <Route
          path="admin/content/edit/:id"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <EditArticle />
            </RoleRoute>
          }
        />

        <Route
          path="admin/quiz-management"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <QuizManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/review"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <ReviewManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/users"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <UserManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/ai-settings"
          element={
            <RoleRoute allowedRoles={MANAGER_ROLES}>
              <AISettings />
            </RoleRoute>
          }
        />

        <Route
          path="admin/notion-sync"
          element={
            <RoleRoute allowedRoles={MANAGER_ROLES}>
              <NotionSync />
            </RoleRoute>
          }
        />

        <Route
          path="admin/analytics"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <Analytics />
            </RoleRoute>
          }
        />

        <Route
          path="admin/security"
          element={
            <RoleRoute allowedRoles={MANAGEMENT_ROLES}>
              <SecurityMonitoring />
            </RoleRoute>
          }
        />
      </Route>

      {/* Return unknown URLs to the home route, where ProtectedRoute verifies the session. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
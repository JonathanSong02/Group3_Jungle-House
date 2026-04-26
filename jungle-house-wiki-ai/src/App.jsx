import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import RoleRoute from './components/RoleRoute';
import { useAuth } from './context/AuthContext';

import Login from './pages/Login';
import Register from "./pages/Register";
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import KnowledgeBase from './pages/KnowledgeBase';
import ArticleDetail from './pages/ArticleDetail';
import Escalation from './pages/Escalation';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import QuizList from './pages/QuizList';

import AddArticle from './pages/admin/AddArticle';
import ContentManagement from './pages/admin/ContentManagement';
import ReviewManagement from './pages/admin/ReviewManagement';
import UserManagement from './pages/admin/UserManagement';
import AISettings from './pages/admin/AISettings';
import Analytics from './pages/admin/Analytics';
import SecurityMonitoring from './pages/admin/SecurityMonitoring';

import SOPSelection from "./pages/SOPSelection";

function HomeRedirect() {
  const { user } = useAuth();

  if (user?.role === 'manager') {
    return <Navigate to="/admin/content" replace />;
  }

  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <Routes>

      {/* PUBLIC ROUTES */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* PROTECTED ROUTES */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />

        {/* STAFF + TEAM LEAD ONLY */}
        <Route
          path="dashboard"
          element={
            <RoleRoute allowedRoles={['staff', 'teamlead']}>
              <Dashboard />
            </RoleRoute>
          }
        />

        <Route
          path="knowledge"
          element={
            <RoleRoute allowedRoles={['staff', 'teamlead']}>
              <KnowledgeBase />
            </RoleRoute>
          }
        />

        <Route
          path="knowledge/:id"
          element={
            <RoleRoute allowedRoles={['staff', 'teamlead']}>
              <ArticleDetail />
            </RoleRoute>
          }
        />

        <Route
          path="notifications"
          element={
            <RoleRoute allowedRoles={['staff', 'teamlead']}>
              <Notifications />
            </RoleRoute>
          }
        />

        <Route
          path="quiz"
          element={
            <RoleRoute allowedRoles={['staff', 'teamlead']}>
              <QuizList />
            </RoleRoute>
          }
        />

        <Route
          path="sop-selection"
          element={
            <RoleRoute allowedRoles={['staff', 'teamlead']}>
              <SOPSelection />
            </RoleRoute>
          }
        />

        {/* ALL LOGIN USERS */}
        <Route path="chat" element={<Chat />} />
        <Route path="profile" element={<Profile />} />

        {/* TEAM LEAD + MANAGER */}
        <Route
          path="escalation"
          element={
            <RoleRoute allowedRoles={['teamlead', 'manager']}>
              <Escalation />
            </RoleRoute>
          }
        />

        {/* MANAGER ONLY */}
        <Route
          path="admin/content"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <ContentManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/content/add"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <AddArticle />
            </RoleRoute>
          }
        />

        <Route
          path="admin/review"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <ReviewManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/users"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <UserManagement />
            </RoleRoute>
          }
        />

        <Route
          path="admin/ai-settings"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <AISettings />
            </RoleRoute>
          }
        />

        <Route
          path="admin/analytics"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <Analytics />
            </RoleRoute>
          }
        />

        <Route
          path="admin/security"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <SecurityMonitoring />
            </RoleRoute>
          }
        />
      </Route>

      {/* FALLBACK */}
      <Route path="*" element={<Navigate to="/login" replace />} />

    </Routes>
  );
}
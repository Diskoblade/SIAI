import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import AdminRoute from "./components/AdminRoute.jsx";
import LandingPage from "./pages/LandingPage.jsx";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Documents from "./pages/Documents.jsx";
import Recent from "./pages/Recent.jsx";
import Admin from "./pages/Admin.jsx";
import DeveloperWorkspace from "./pages/DeveloperWorkspace.jsx";
import ApprovalNotes from "./pages/ApprovalNotes.jsx";
import ApprovalNoteEditor from "./pages/ApprovalNoteEditor.jsx";
import AdminApprovalNotes from "./pages/AdminApprovalNotes.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/documents"
        element={
          <ProtectedRoute>
            <Documents />
          </ProtectedRoute>
        }
      />
      <Route
        path="/recent"
        element={
          <ProtectedRoute>
            <Recent />
          </ProtectedRoute>
        }
      />
      <Route
        path="/code"
        element={
          <ProtectedRoute>
            <DeveloperWorkspace />
          </ProtectedRoute>
        }
      />
      <Route
        path="/approval-notes"
        element={
          <ProtectedRoute>
            <ApprovalNotes />
          </ProtectedRoute>
        }
      />
      <Route
        path="/approval-notes/:id/edit"
        element={
          <ProtectedRoute>
            <ApprovalNoteEditor />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/approval-notes"
        element={
          <AdminRoute>
            <AdminApprovalNotes />
          </AdminRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <AdminRoute>
            <Admin />
          </AdminRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

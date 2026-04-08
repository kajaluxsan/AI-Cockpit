import { Route, Routes, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import PeopleTab from "./components/PeopleTab";
import MessagesTab from "./components/MessagesTab";
import JobsTab from "./components/JobsTab";
import CandidateDetail from "./components/CandidateDetail";
import JobDetail from "./components/JobDetail";
import Dashboard from "./components/Dashboard";
import MatchBoard from "./components/MatchBoard";
import CallHistory from "./components/CallHistory";
import EmailLog from "./components/EmailLog";
import Settings from "./components/Settings";
import { ChatDockProvider } from "./components/chat/ChatDockContext";
import ChatDock from "./components/chat/ChatDock";

export default function App() {
  return (
    <ChatDockProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/people" replace />} />
          <Route path="people" element={<PeopleTab />} />
          <Route path="people/:id" element={<CandidateDetail />} />
          <Route path="messages" element={<MessagesTab />} />
          <Route path="jobs" element={<JobsTab />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="overview" element={<Dashboard />} />
          <Route path="matches" element={<MatchBoard />} />
          <Route path="calls" element={<CallHistory />} />
          <Route path="emails" element={<EmailLog />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
      <ChatDock />
    </ChatDockProvider>
  );
}

import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./components/Dashboard";
import CandidateList from "./components/CandidateList";
import CandidateDetail from "./components/CandidateDetail";
import JobList from "./components/JobList";
import JobDetail from "./components/JobDetail";
import MatchBoard from "./components/MatchBoard";
import CallHistory from "./components/CallHistory";
import EmailLog from "./components/EmailLog";
import Settings from "./components/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="candidates" element={<CandidateList />} />
        <Route path="candidates/:id" element={<CandidateDetail />} />
        <Route path="jobs" element={<JobList />} />
        <Route path="jobs/:id" element={<JobDetail />} />
        <Route path="matches" element={<MatchBoard />} />
        <Route path="calls" element={<CallHistory />} />
        <Route path="emails" element={<EmailLog />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}

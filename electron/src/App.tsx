import { useEffect } from 'react';
import { HashRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import Home from './pages/Home';
import Chat from './pages/Chat';
import Settings from './pages/Settings';
import Permissions from './pages/permissions';
import Graph from './pages/Graph';
import Dashboard from './pages/Dashboard';
import Welcome from './pages/onboarding/Welcome';
import UserProfile from './pages/onboarding/UserProfile';
import ApiKey from './pages/onboarding/ApiKey';
import SetupComplete from './pages/onboarding/SetupComplete';

// Component to handle tray navigation events
function TrayNavigationHandler() {
  const navigate = useNavigate();

  useEffect(() => {
    // Listen for open settings from tray or Cmd+,
    const unsubscribeSettings = window.traceAPI.tray.onOpenSettings(() => {
      navigate('/settings');
    });

    // Listen for open graph from tray
    const unsubscribeGraph = window.traceAPI.tray.onOpenGraph(() => {
      navigate('/graph');
    });

    return () => {
      unsubscribeSettings();
      unsubscribeGraph();
    };
  }, [navigate]);

  return null;
}

function App() {
  return (
    <ErrorBoundary>
      <HashRouter>
        <TrayNavigationHandler />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/permissions" element={<Permissions />} />
          <Route path="/graph" element={<Graph />} />
          <Route path="/dashboard" element={<Dashboard />} />
          {/* Onboarding routes */}
          <Route path="/onboarding/welcome" element={<Welcome />} />
          <Route path="/onboarding/profile" element={<UserProfile />} />
          <Route path="/onboarding/api-key" element={<ApiKey />} />
          <Route path="/onboarding/complete" element={<SetupComplete />} />
        </Routes>
      </HashRouter>
    </ErrorBoundary>
  );
}

export default App;

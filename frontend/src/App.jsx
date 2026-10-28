import React from 'react';
import { BrowserRouter as Router, Navigate, Route, Routes } from 'react-router-dom';
import Home from './pages/Home';
import Brief from './pages/Brief';
import Audit from './pages/Audit';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/brief" element={<Brief />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/analyze" element={<Navigate to="/brief" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

// Import components and pages
import Navbar from './components/Navbar';
import Home from './pages/Home';
import './App.css'; 

function App() {
  return (
    <Router>
      <div className="app-container">
        
        {/* The Navbar sits OUTSIDE the Routes so it shows on every page */}
        <Navbar />
        
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>

      </div>
    </Router>
  );
}


export default App;
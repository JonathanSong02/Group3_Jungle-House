import React from 'react';
import { Link } from 'react-router-dom';
import '../css/Navbar.css';

const Navbar = () => {
  return (
    <nav className="navbar">
      {/* Brand Logo */}
      <div className="navbar-brand">
        <Link to="/">
          <span className="logo-icon">🍯</span>
          Jungle House
        </Link>
      </div>

      {/* Center Links */}
      <ul className="navbar-links">
        <li><Link to="/">Home</Link></li>
        <li><Link to="/shop">Shop Honey</Link></li>
      </ul>

      {/* Right Side Actions (Login & Cart) */}
      <div className="navbar-actions">
        <Link to="/login" className="nav-login">Login</Link>
        <Link to="/cart" className="nav-cart">
          🛒 Cart
          <span className="cart-badge">0</span>
        </Link>
      </div>
    </nav>
  );
};

export default Navbar;
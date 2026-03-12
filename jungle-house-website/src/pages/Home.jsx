import React from 'react';
import { Link } from 'react-router-dom';

// Notice the updated import path below:
// It goes up one folder (../), then into the css folder
import '../css/Home.css'; 

const Home = () => {
  return (
    <div className="home-container">
      
      {/* 1. HERO SECTION */}
      <section className="hero-section">
        <div className="hero-content">
          <h1>Pure, Natural Honey from the Heart of Borneo</h1>
          <p>
            Experience the finest 100% natural, raw, and organic honey, 
            ethically sourced from native beekeepers.
          </p>
          <Link to="/shop" className="btn-primary">
            Shop Our Honey
          </Link>
        </div>
      </section>

      {/* 2. FEATURED PRODUCTS SECTION */}
      <section className="featured-section">
        <h2>Our Bestsellers</h2>
        <p>Discover our customers' favorite natural health boosters.</p>
        
        <div className="product-grid">
          {/* Product Card 1 */}
          <div className="product-card">
            <div className="image-placeholder">🍯 Royal Black Honey</div>
            <h3>Royal Black Honey</h3>
            <p>RM 65.00</p>
            <button className="btn-secondary">Add to Cart</button>
          </div>
          
          {/* Product Card 2 */}
          <div className="product-card">
            <div className="image-placeholder">🍯 Premium Wild Honey</div>
            <h3>Premium Wild Honey</h3>
            <p>RM 55.00</p>
            <button className="btn-secondary">Add to Cart</button>
          </div>
          
          {/* Product Card 3 */}
          <div className="product-card">
            <div className="image-placeholder">🍯 Honey Gift Set</div>
            <h3>Classic Gift Set</h3>
            <p>RM 120.00</p>
            <button className="btn-secondary">Add to Cart</button>
          </div>
        </div>
      </section>

      {/* 3. BRAND MISSION & ETHICS SECTION */}
      <section className="mission-section">
        <h2>More Than Just Honey</h2>
        <div className="mission-content">
          <div className="mission-item">
            <h3>🐝 Ethical Beekeeping</h3>
            <p>We partner with rural communities to promote sustainable methods that protect the environment.</p>
          </div>
          <div className="mission-item">
            <h3>🌿 100% Natural & Raw</h3>
            <p>No additives, no artificial sugars. Just pure wellness straight from the hive to your home.</p>
          </div>
          <div className="mission-item">
            <h3>💛 Empowering Communities</h3>
            <p>Every purchase supports local farmers and helps build a sustainable future in Sarawak.</p>
          </div>
        </div>
      </section>

    </div>
  );
};

export default Home;
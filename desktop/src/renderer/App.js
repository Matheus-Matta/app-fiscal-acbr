import React, { useState } from 'react';
import './App.css';
import LoginPage from './pages/LoginPage';
import RestaurantPage from './pages/RestaurantPage';
import DashboardPage from './pages/DashboardPage';

function App() {
  const [page, setPage] = useState('login'); // login, restaurant, dashboard
  const [token, setToken] = useState('');
  const [restaurantId, setRestaurantId] = useState('');

  const handleLoginSuccess = (token) => {
    setToken(token);
    setPage('restaurant');
  };

  const handleRestaurantSelect = (restaurantId) => {
    setRestaurantId(restaurantId);
    setPage('dashboard');
  };

  return (
    <div className="app">
      {page === 'login' && <LoginPage onSuccess={handleLoginSuccess} />}
      {page === 'restaurant' && (
        <RestaurantPage token={token} onSelect={handleRestaurantSelect} />
      )}
      {page === 'dashboard' && (
        <DashboardPage token={token} restaurantId={restaurantId} />
      )}
    </div>
  );
}

export default App;

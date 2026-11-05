import React, { useState, useEffect } from 'react';
import '../styles/RestaurantPage.css';

function RestaurantPage({ token, onSelect }) {
  const [restaurants, setRestaurants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadRestaurants = async () => {
      try {
        const result = await window.api.getRestaurants(token);
        if (result.success) {
          setRestaurants(result.restaurants);
        } else {
          setError(result.error || 'Erro ao carregar restaurantes');
        }
      } catch (err) {
        setError('Erro de conexão');
      } finally {
        setLoading(false);
      }
    };

    loadRestaurants();
  }, [token]);

  const handleSelectRestaurant = async (restaurantId) => {
    setSyncing(restaurantId);
    try {
      const result = await window.api.syncData(token, restaurantId);
      if (result.success) {
        onSelect(restaurantId);
      } else {
        setError(result.error || 'Erro ao sincronizar dados');
      }
    } catch (err) {
      setError('Erro de conexão');
    } finally {
      setSyncing(null);
    }
  };

  return (
    <div className="restaurant-page">
      <div className="restaurant-container">
        <div className="restaurant-header">
          <h1>Selecione um Restaurante</h1>
          <p>Escolha qual restaurante deseja usar para emissão fiscal</p>
        </div>

        {error && <div className="error-message">{error}</div>}

        {loading ? (
          <div className="loading">Carregando restaurantes...</div>
        ) : restaurants.length === 0 ? (
          <div className="empty-state">
            <p>Nenhum restaurante disponível</p>
          </div>
        ) : (
          <div className="restaurant-list">
            {restaurants.map((restaurant) => (
              <div key={restaurant.id} className="restaurant-card">
                <div className="restaurant-info">
                  <h3>{restaurant.name}</h3>
                  <p>CNPJ: {restaurant.cnpj}</p>
                  <p className="uf">UF: {restaurant.uf}</p>
                </div>
                <button
                  onClick={() => handleSelectRestaurant(restaurant.id)}
                  disabled={syncing !== null}
                  className="btn-select"
                >
                  {syncing === restaurant.id ? 'Sincronizando...' : 'Selecionar'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default RestaurantPage;

import React from 'react';
import '../styles/DashboardPage.css';

function DashboardPage({ token, restaurantId }) {
  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <h1>Dashboard - Pronto para Comunicação</h1>
      </div>

      <div className="dashboard-content">
        <div className="status-card">
          <h2>Status do Serviço</h2>
          <div className="status-item">
            <span>API Local:</span>
            <span className="status-ok">🟢 Ativo</span>
          </div>
          <div className="status-item">
            <span>Restaurante:</span>
            <span>{restaurantId}</span>
          </div>
          <div className="status-item">
            <span>Endereço PDV:</span>
            <span className="endpoint">http://localhost:8001</span>
          </div>
        </div>

        <div className="info-card">
          <h2>Configuração PDV</h2>
          <p>O PDV deve conectar no seguinte endereço:</p>
          <div className="code-block">
            <code>http://localhost:8001/v1/status-servico</code>
          </div>
          <p style={{ marginTop: '1rem', fontSize: '0.9rem', color: '#666' }}>
            Todas as requisições devem incluir o header:
          </p>
          <div className="code-block">
            <code>Authorization: Bearer [token]</code>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;

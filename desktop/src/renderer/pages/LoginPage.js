import React, { useState } from 'react';
import '../styles/LoginPage.css';

function LoginPage({ onSuccess }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const result = await window.api.login(email, password);
      if (result.success) {
        onSuccess(result.token);
      } else {
        setError(result.error || 'Erro ao fazer login');
      }
    } catch (err) {
      setError('Erro de conexão');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>StarChef Fiscal</h1>
          <p>Sistema de Emissão de Notas Fiscais</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Senha</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Autenticando...' : 'Entrar'}
          </button>
        </form>

        <div className="login-footer">
          <p>v1.0.0 - Offline</p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;

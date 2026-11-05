# StarChef - Comunicador Fiscal ACBr

Sistema de emissão de notas fiscais com duas arquiteturas:

- **`server/`** → API Docker para comunicação SEFAZ (produção/APIs)
- **`desktop/`** → Instalador Windows para PDV offline (sem depender de API)

## Arquitetura

### 1. Servidor (Docker)
- FastAPI + ACBrLib
- Comunica com SEFAZ
- Autenticação por token Bearer
- Pronto para orquestração

### 2. Desktop (Windows Installer)
- Electron + React
- Login + Seleção de Restaurante
- Sincroniza dados fiscais
- PDV conecta localmente (http://localhost:8001)
- Funciona offline após sincronização

## Quick Start

### Servidor
```bash
cd server
docker build -t fiscal-acbr .
docker run -p 8001:8001 fiscal-acbr
```

### Desktop
```bash
cd desktop
npm install
npm start  # desenvolvimento
npm run build  # gera .exe
```

## Referência
Baseado em: https://github.com/Matheus-Matta/starchef (branch release/v3.0.0)

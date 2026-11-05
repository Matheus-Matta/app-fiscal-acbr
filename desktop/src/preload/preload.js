const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  login: (email, password) =>
    ipcRenderer.invoke('login', { email, password }),

  getRestaurants: (token) =>
    ipcRenderer.invoke('get-restaurants', token),

  syncData: (token, restaurantId) =>
    ipcRenderer.invoke('sync-data', { token, restaurantId }),
});

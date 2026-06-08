import axios from 'axios';
import { fetchAuthToken } from './authService';

const BASE_URL = 'https://transmission-api-v3.unada.in';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

let cachedToken: string | null = null;

// Function to get token, fetching it if not present
export const getAccessToken = async (): Promise<string | null> => {
  if (cachedToken) {
    return cachedToken;
  }
  
  // Try to load from localStorage first
  const storedToken = localStorage.getItem('transmission_auth_token');
  if (storedToken) {
    cachedToken = storedToken;
    return cachedToken;
  }

  // Otherwise fetch from powerback API
  const newToken = await fetchAuthToken();
  if (newToken) {
    cachedToken = newToken;
    localStorage.setItem('transmission_auth_token', newToken);
    return cachedToken;
  }

  return null;
};

// Request interceptor to add the token
apiClient.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

import axios from 'axios';

const AUTH_URL = 'https://powerback-api.unada.in/api/v1/user/login';
const CREDENTIALS = {
  email: 'zaid@unada.io',
  password: 'Demo@123'
};

export const fetchAuthToken = async (): Promise<string | null> => {
  try {
    const response = await axios.post(AUTH_URL, CREDENTIALS);
    const data = response.data;
    
    // As per user provided postman script logic
    if (data.token) {
      return data.token;
    } else if (data.data && data.data.token) {
      return data.data.token;
    } else if (data.access_token) {
      return data.access_token;
    }
    
    console.warn('Token not found in response:', data);
    return null;
  } catch (error) {
    console.error('Error fetching auth token:', error);
    return null;
  }
};

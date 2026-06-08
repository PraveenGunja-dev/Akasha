import { apiClient } from './apiClient';

export const rajasthanApi = {
  getHealth: async () => {
    const res = await apiClient.get('/api/rajasthan/health');
    return res.data;
  },
  getDefaultData: async () => {
    const res = await apiClient.get('/api/rajasthan/default-data');
    return res.data;
  },
  getCurrentData: async () => {
    const res = await apiClient.get('/api/rajasthan/current-data');
    return res.data;
  },
  getProjects: async () => {
    const res = await apiClient.get('/api/rajasthan/projects');
    return res.data;
  },
  getProjectById: async (id: string) => {
    const res = await apiClient.get(`/api/rajasthan/projects/${id}`);
    return res.data;
  }
};

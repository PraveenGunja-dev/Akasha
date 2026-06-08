import { apiClient } from './apiClient';

export const khavdaApi = {
  getHealth: async () => {
    const res = await apiClient.get('/api/khavda/health');
    return res.data;
  },
  getDefaultData: async () => {
    const res = await apiClient.get('/api/khavda/default-data');
    return res.data;
  },
  getCurrentData: async () => {
    const res = await apiClient.get('/api/khavda/current-data');
    return res.data;
  },
  getProjects: async () => {
    const res = await apiClient.get('/api/khavda/projects');
    return res.data;
  },
  getProjectById: async (id: string) => {
    const res = await apiClient.get(`/api/khavda/projects/${id}`);
    return res.data;
  },
  getHierarchy: async () => {
    const res = await apiClient.get('/api/khavda/hierarchy');
    return res.data;
  },
  getHierarchyStats: async () => {
    const res = await apiClient.get('/api/khavda/hierarchy/stats');
    return res.data;
  },
  getHierarchyPaths: async () => {
    const res = await apiClient.get('/api/khavda/hierarchy/paths');
    return res.data;
  }
};

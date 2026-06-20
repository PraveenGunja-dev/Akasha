export interface ProjectMapping {
  id: number;
  project?: string;
  spv_name?: string;
  project_id?: string;
  project_name_from_p6?: string;
  plot_no?: string;
  category?: string;
  mms_type?: string;
  capacity_mwac?: number;
  ol?: string;
  capacity_mwdc?: number;
  spv_plant_code?: string;
  agel?: string;
  module_wbs?: string;
  age6l?: string;
  cluster?: string;
  not_allocated?: string;
  source_of_origin?: string;
  priority?: string;
}

export type ProjectMappingCreate = Omit<ProjectMapping, 'id'>;

export const fetchMappings = async (): Promise<ProjectMapping[]> => {
  const response = await fetch('/akasha/api/mappings/');
  if (!response.ok) {
    throw new Error('Failed to fetch mappings');
  }
  return response.json();
};

export interface UnmappedOptions {
  unmapped_transmission: string[];
  unmapped_p6: string[];
}

export const fetchUnmappedOptions = async (): Promise<UnmappedOptions> => {
  const response = await fetch('/akasha/api/mappings/unmapped/options');
  if (!response.ok) {
    throw new Error('Failed to fetch unmapped options');
  }
  return response.json();
};

export const createMapping = async (mapping: ProjectMappingCreate): Promise<ProjectMapping> => {
  const response = await fetch('/akasha/api/mappings/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(mapping),
  });
  if (!response.ok) {
    throw new Error('Failed to create mapping');
  }
  return response.json();
};

export const updateMapping = async (id: number, mapping: Partial<ProjectMappingCreate>): Promise<ProjectMapping> => {
  const response = await fetch(`/akasha/api/mappings/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(mapping),
  });
  if (!response.ok) {
    throw new Error('Failed to update mapping');
  }
  return response.json();
};

export const deleteMapping = async (id: number): Promise<void> => {
  const response = await fetch(`/akasha/api/mappings/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error('Failed to delete mapping');
  }
};

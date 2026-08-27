export type UserRole =
  | 'super_admin'
  | 'consultant'
  | 'institution_admin'
  | 'iqac_coordinator'
  | 'registrar'
  | 'hod'
  | 'hr_officer'
  | 'lab_admin'
  | 'placement_officer'
  | 'faculty'
  | 'viewer';

export interface User {
  id: string;
  institution_id: string | null;
  username: string;
  name: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  role: UserRole;
  department_name: string;
  is_active: boolean;
  is_staff: boolean;
  date_joined: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

export type UserRole =
  | 'super_admin'
  | 'consultant'
  | 'iqac_coordinator';

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

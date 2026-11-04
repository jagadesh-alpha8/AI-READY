import { http } from './http';
import type { AdminUser } from '../types/api';

export const listUsers = () => http.get<AdminUser[]>('/users');

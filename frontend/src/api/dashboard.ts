import api from './client';
import type { DashboardData } from '../types';

export function getDashboard() {
  return api.get<DashboardData>('/dashboard');
}

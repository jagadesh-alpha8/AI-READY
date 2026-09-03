export interface Institution {
  id: string;
  name: string;
  short_name: string;
  institution_type: string;
  university_affiliation: string;
  affiliation: string;
  website_url: string;
  location: string;
  city: string;
  state: string;
  country: string;
  accreditation_details: string;
  accreditation_status: string;
  contact_email: string;
  contact_phone: string;
  is_active: boolean;
  sprint_count: number;
  // --- Institution DNA ---
  student_count: number | null;
  faculty_count: number | null;
  priorities: string[];
  digital_maturity_level: number | null;
  current_ai_usage: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * What `GET /institutions/{id}` returns. The extra fields cost a query or a
 * prefetch each, so the backend only serves them on the single-record read —
 * the list endpoint returns plain `Institution` rows.
 */
export interface InstitutionDetail extends Institution {
  leaders: InstitutionLeader[];
  /** Derived from the department rows, never stored. */
  department_count: number;
  /** Summed from the departments' own programme counts. */
  program_count: number;
  digital_maturity_label: string;
  digital_maturity_description: string;
}

export interface InstitutionLeader {
  id: string;
  name: string;
  role: string;
  email: string;
  /** Derived from the name by the backend, for the avatar. */
  initials: string;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  name: string;
  head_name: string;
  faculty_count: number;
  student_count: number;
  program_count: number;
  display_order: number;
  created_at: string;
  updated_at: string;
}

/** Blank for an ordinary system; the two values mark what blocks AI readiness. */
export type InstitutionSystemTag = '' | 'legacy' | 'manual';

export interface InstitutionSystem {
  id: string;
  name: string;
  tag: InstitutionSystemTag;
  tag_label: string;
  notes: string;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface CreateInstitutionPayload {
  name: string;
  institution_type?: string;
  city?: string;
  state?: string;
  affiliation?: string;
  accreditation_status?: string;
  website_url?: string;
}

export type UpdateInstitutionPayload = Partial<
  Pick<
    Institution,
    | 'name'
    | 'institution_type'
    | 'city'
    | 'state'
    | 'location'
    | 'website_url'
    | 'accreditation_details'
    | 'student_count'
    | 'faculty_count'
    | 'priorities'
    | 'digital_maturity_level'
    | 'current_ai_usage'
  >
> & { affiliation?: string };

export type DepartmentPayload = Partial<
  Pick<Department, 'name' | 'head_name' | 'faculty_count' | 'student_count' | 'program_count'>
>;

export type InstitutionSystemPayload = Partial<
  Pick<InstitutionSystem, 'name' | 'tag' | 'notes'>
>;

export type InstitutionLeaderPayload = Partial<Pick<InstitutionLeader, 'name' | 'role' | 'email'>>;

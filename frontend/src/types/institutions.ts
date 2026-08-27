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
  created_by: string | null;
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

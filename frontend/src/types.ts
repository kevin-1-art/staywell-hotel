export type Role = 'admin' | 'manager' | 'front_desk' | 'housekeeping' | 'accountant';

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
};

export type Session = {
  access_token: string;
  token_type: 'bearer';
  user: User;
};
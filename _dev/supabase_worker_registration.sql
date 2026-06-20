alter table public.profiles
    add column if not exists full_name text;

alter table public.profiles
    add column if not exists contact text;

alter table public.profiles
    add column if not exists nationality text;

alter table public.profiles
    add column if not exists is_approved boolean default false;

alter table public.profiles
    add column if not exists signup_status text default 'pending';

alter table public.profiles
    add column if not exists signup_source text;

alter table public.profiles
    add column if not exists terms_accepted_at timestamptz;

alter table public.profiles
    add column if not exists privacy_accepted_at timestamptz;

alter table public.profiles
    add column if not exists pin_code varchar(4) default '1234';

alter table public.profiles
    add column if not exists membership text default 'std';


-- 🛡️ Picadiri Studio DB Migration Script
-- Run this in your Supabase SQL Editor

-- 1. Create profiles table if not exists (or update it)
-- Usually profiles is linked to auth.users
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID REFERENCES auth.users(id) PRIMARY KEY,
    email TEXT,
    membership TEXT DEFAULT 'standard',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Add membership fallback trigger (optional but recommended)
-- Ensure every new user has a 'standard' membership
CREATE OR REPLACE FUNCTION public.handle_new_user() 
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, membership)
  VALUES (new.id, new.email, 'standard');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: create profile on signup
-- DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
-- CREATE TRIGGER on_auth_user_created
--   AFTER INSERT ON auth.users
--   FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- 3. Create publishing_requests table
CREATE TABLE IF NOT EXISTS public.publishing_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    video_url TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'published')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Enable RLS
ALTER TABLE public.publishing_requests ENABLE ROW LEVEL SECURITY;

-- 5. Policies
-- Users can see their own requests
CREATE POLICY "Users can view own requests" ON public.publishing_requests
    FOR SELECT USING (auth.uid() = user_id);

-- Users can insert their own requests
CREATE POLICY "Users can create own requests" ON public.publishing_requests
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Admins can view and update everything
-- Replace your admin email here
CREATE POLICY "Admins can manage all requests" ON public.publishing_requests
    FOR ALL USING (auth.jwt() ->> 'email' = 'ejsh0519@naver.com');

-- 6. Add profiles link (Foreign Key for easier joining in UI)
-- Already added in CREATE TABLE step above.

-- 7. Storage Bucket Setup (IMPORTANT)
-- Go to Storage -> New Bucket -> Name: "videos" -> Public: ON
-- Or run this if your Supabase version supports it:
-- INSERT INTO storage.buckets (id, name, public) VALUES ('videos', 'videos', true);

-- Add policy to allow public viewing
CREATE POLICY "Public Access" ON storage.objects FOR SELECT USING (bucket_id = 'videos');

-- Add policy to allow authenticated uploads (Central server handles this via Admin key, but helpful for debugging)
-- CREATE POLICY "Upload Access" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'videos');

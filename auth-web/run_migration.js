const { Client } = require('pg');
require('dotenv').config({ path: './.env.local' });
if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
  // If not in .env.local, check parent .env
  require('dotenv').config({ path: '../.env' });
}

const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
// PostgREST doesn't allow executing arbitrary SQL, but we can connect via direct PostgreSQL connection string!
// The standard connection string format for Supabase is:
// postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
// Since we have the project reference (giorysjpgxzdypbmxwmx) and the Service Role Key, we can actually use the HTTP REST SQL endpoint if we have a custom RPC,
// OR we can ask the user for the DB Password if direct SQL connection is needed.
// Wait! Let's check if we can make a schema migration using the Supabase Admin client or REST API.
// PostgREST REST API allows reading/writing to existing tables, but does not allow running arbitrary DDL (CREATE TABLE) unless we invoke a stored procedure.
//
// But wait! We can write a script that updates the tables using standard HTTP REST API endpoints, or prints the exact SQL statements so the user can easily run them.
// Let's first try to check if we can create or run a migration script.
// Let's output a helper node script that outputs the SQL migration code clearly.

console.log("=== SUPABASE SQL SCHEMA MIGRATION ===");
console.log("Supabase URL:", url);
console.log("Please run the following SQL statements in the Supabase Dashboard SQL Editor (https://supabase.com/dashboard/project/giorysjpgxzdypbmxwmx/sql/new):");
console.log(`
-- 1. 카테고리 테이블 생성
CREATE TABLE IF NOT EXISTS public.categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    keywords TEXT,
    benchmark_channel_url TEXT,
    assigned_employee_email TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. AI 주제 대기열 테이블 생성
CREATE TABLE IF NOT EXISTS public.topics_queue (
    id SERIAL PRIMARY KEY,
    category_id INT REFERENCES public.categories(id) ON DELETE SET NULL,
    topic TEXT NOT NULL,
    assigned_employee_email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'assigned' | 'completed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    assigned_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- 3. profiles 테이블에 핀 번호 컬럼 추가 (PIN 4자리)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema='public' 
        AND table_name='profiles' 
        AND column_name='pin_code'
    ) THEN
        ALTER TABLE public.profiles ADD COLUMN pin_code VARCHAR(4) DEFAULT '1234';
    END IF;
END $$;

-- 4. 시스템 전역 설정 (API 키 등) 테이블 생성
CREATE TABLE IF NOT EXISTS public.global_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. 원격 비디오 렌더링 순차 큐 및 진행 정보 관리용 테이블 생성
CREATE TABLE IF NOT EXISTS public.remote_render_queue (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   INTEGER NOT NULL,
    project_name TEXT,
    email        TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    progress     INTEGER DEFAULT 0,
    message      TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
`);

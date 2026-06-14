import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("Error: Missing credentials")
    exit(1)

# SQL 실행을 위해 Supabase Management 혹은 Postgres REST RPC 호출을 처리해야 함.
# 기본 PostgREST API를 통한 SQL 직접 실행은 불가능하지만, 
# Supabase는 기본적으로 schema, table 생성을 REST API를 통한 RPC 또는 직접 DDL SQL 덤프 호출로 지원하지 않음.
# 그러나 DB admin SQL Execution Endpoint 가 있거나, raw DB API (postgres protocol)가 가능함.
# 파이썬에서 psycopg2를 써서 직접 PostgreSQL에 접속하여 실행하거나
# 또는 Vercel/어드민 코드에 Next.js API가 있다면 그걸 사용하는 방법이 있습니다.
# 먼저 로컬 python에 pg/psycopg2가 설치되어 있는지 확인하거나, sqlite DB 검사를 위해 작성된
# check_remote_tables.py의 endpoint를 이용해 쿼리 실행을 할 수 있는 rpc가 있는지 확인합니다.

# 데이터베이스 생성을 위한 DDL SQL 구문:
sql_statements = """
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
"""

print("SQL 구문 준비 완료:")
print(sql_statements)

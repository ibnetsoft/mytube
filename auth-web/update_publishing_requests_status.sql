-- =============================================================
-- Supabase DB: publishing_requests status 제약조건(CHECK) 업데이트
-- Supabase 대시보드 > SQL Editor 에서 아래 쿼리를 전체 실행하세요.
-- =============================================================

-- 1. 기존 제약 조건(Constraint) 제거
ALTER TABLE public.publishing_requests 
DROP CONSTRAINT IF EXISTS publishing_requests_status_check;

-- 2. 새 상태('to_be_published', 'failed')가 포함된 새로운 제약 조건 추가
ALTER TABLE public.publishing_requests 
ADD CONSTRAINT publishing_requests_status_check 
CHECK (status IN ('pending', 'approved', 'rejected', 'published', 'to_be_published', 'failed'));

-- 3. 확인용 쿼리 (제약 조건 목록 조회)
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'public.publishing_requests'::regclass;

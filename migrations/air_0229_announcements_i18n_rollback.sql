-- Rollback for AIR-0229 — 공지사항 게시판 다국어 자동번역
-- auth-web/migration_announcements.sql(PR #104)이 만든 announcements 테이블
-- 자체는 이 마이그레이션이 만든 게 아니므로 건드리지 않는다.
-- AIR-0229가 추가한 컬럼만 되돌린다.

ALTER TABLE public.announcements DROP COLUMN IF EXISTS title_en;
ALTER TABLE public.announcements DROP COLUMN IF EXISTS body_en;
ALTER TABLE public.announcements DROP COLUMN IF EXISTS title_vi;
ALTER TABLE public.announcements DROP COLUMN IF EXISTS body_vi;
ALTER TABLE public.announcements DROP COLUMN IF EXISTS title_th;
ALTER TABLE public.announcements DROP COLUMN IF EXISTS body_th;
ALTER TABLE public.announcements DROP COLUMN IF EXISTS translation_status;

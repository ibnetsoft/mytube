
-- ai_logs 테이블이 없으면 생성하고, 있으면 필요한 컬럼 추가
CREATE TABLE IF NOT EXISTS public.ai_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task_type TEXT,
    model_id TEXT,
    provider TEXT,
    status TEXT,
    prompt_summary TEXT,
    error_msg TEXT,
    elapsed_time REAL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 기존 테이블이 있는 경우 컬럼 추가 (Safe update)
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ai_logs' AND COLUMN_NAME='input_tokens') THEN
        ALTER TABLE public.ai_logs ADD COLUMN input_tokens INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ai_logs' AND COLUMN_NAME='output_tokens') THEN
        ALTER TABLE public.ai_logs ADD COLUMN output_tokens INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ai_logs' AND COLUMN_NAME='elapsed_time') THEN
        ALTER TABLE public.ai_logs ADD COLUMN elapsed_time REAL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ai_logs' AND COLUMN_NAME='balance_after') THEN
        ALTER TABLE public.ai_logs ADD COLUMN balance_after INTEGER;
    END IF;
END $$;

-- 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_ai_logs_user_id ON public.ai_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_logs_created_at ON public.ai_logs(created_at DESC);

# AIR Studio — Supabase Migration 적용 순서 및 검증 체크리스트

## 사전 조건

- PR #31 (AIR-0128) 가 main에 merge된 상태여야 합니다.
- PR #32 (AIR-0129) 가 main에 merge된 상태여야 합니다.
- Supabase Dashboard SQL Editor 접근 권한 필요.

---

## Step 1 — AIR-0128 Migration (6개 번역 컬럼 추가)

**파일**: `migrations/air_0128_topics_queue_translation_columns.sql`

```sql
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS topic_vi           TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS topic_en           TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS topic_th           TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS category_name_vi   TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS category_name_en   TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS category_name_th   TEXT DEFAULT NULL;
```

**적용 방법**:
1. Supabase Dashboard → SQL Editor
2. 위 SQL 붙여넣기 후 실행

**검증 쿼리**:
```sql
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'topics_queue'
  AND column_name IN (
    'topic_vi','topic_en','topic_th',
    'category_name_vi','category_name_en','category_name_th'
  );
```
→ 6개 행이 반환되면 정상.

---

## Step 2 — AIR-0129 Migration (번역 상태 추적 컬럼 추가)

**Step 1 완료 후** 진행.

**파일**: `migrations/air_0129_topics_queue_translation_status.sql`

```sql
ALTER TABLE topics_queue
    ADD COLUMN IF NOT EXISTS translated_at      TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE topics_queue
    ADD COLUMN IF NOT EXISTS translation_status TEXT        DEFAULT NULL
        CHECK (
            translation_status IS NULL
            OR translation_status IN ('pending', 'running', 'completed', 'failed')
        );
```

**적용 방법**:
1. Supabase Dashboard → SQL Editor
2. 위 SQL 붙여넣기 후 실행

**검증 쿼리**:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'topics_queue'
  AND column_name IN ('translated_at', 'translation_status');
```
→ 2개 행 반환, `translated_at`=`timestamp with time zone`, `translation_status`=`text` 이면 정상.

**CHECK 제약 확인**:
```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'topics_queue'::regclass
  AND contype = 'c';
```

---

## Step 3 — auth-web 배포 (Vercel)

두 Migration 완료 후 Vercel에 auth-web을 배포합니다.
배포 전 PR #31 + PR #32 모두 main에 merge되어 있어야 합니다.

---

## Step 4 — 기존 Row Backfill

배포 후, 기존 topics_queue 행에 번역을 채웁니다.

```bash
python scripts/backfill_topic_translations.py --lang vi
python scripts/backfill_topic_translations.py --lang en
python scripts/backfill_topic_translations.py --lang th
```

`--dry-run` 플래그로 실제 저장 없이 미리 확인 가능:
```bash
python scripts/backfill_topic_translations.py --lang vi --dry-run
```

---

## Step 5 — 운영 검증 체크리스트

### 5-1. Admin 번역 파이프라인 검증

1. Admin → Topic 생성 (POST)
2. Supabase에서 해당 row 조회:
   ```sql
   SELECT id, topic, translation_status, translated_at,
          topic_vi, topic_en, topic_th
   FROM topics_queue
   ORDER BY created_at DESC
   LIMIT 1;
   ```
3. 생성 직후: `translation_status = 'pending'` 또는 `'running'` 확인
4. ~30초 후: `translation_status = 'completed'`, `translated_at` 값 존재, `topic_vi/en/th` 채워짐 확인

### 5-2. Admin Topic 수정 검증

1. Admin → 기존 Topic 제목 수정 (PUT)
2. 수정 직후 Supabase 조회:
   - `topic_vi / topic_en / topic_th` = NULL (리셋됨)
   - `translation_status = 'pending'`
3. ~30초 후 재조회:
   - `translation_status = 'completed'`
   - 변경된 제목이 각 언어로 번역되어 저장됨

### 5-3. User App AI 호출 없음 검증

1. Worker로 로그인
2. 언어 스위치 클릭 (한국어 → 베트남어)
3. FastAPI 서버 로그 확인:
   - `translate_recommended_topics` 로그에 `_translate_topics_batch` 호출 없음
   - DB 조회만 수행됨 (Gemini/Claude API 호출 없음)

---

## Rollback

### AIR-0129 Migration 롤백

```sql
ALTER TABLE topics_queue DROP COLUMN IF EXISTS translated_at;
ALTER TABLE topics_queue DROP COLUMN IF EXISTS translation_status;
```

### AIR-0128 Migration 롤백 (AIR-0129 롤백 후)

```sql
ALTER TABLE topics_queue DROP COLUMN IF EXISTS topic_vi;
ALTER TABLE topics_queue DROP COLUMN IF EXISTS topic_en;
ALTER TABLE topics_queue DROP COLUMN IF EXISTS topic_th;
ALTER TABLE topics_queue DROP COLUMN IF EXISTS category_name_vi;
ALTER TABLE topics_queue DROP COLUMN IF EXISTS category_name_en;
ALTER TABLE topics_queue DROP COLUMN IF EXISTS category_name_th;
```

---

## 문제 발생 시

### translation_status가 'completed'가 되지 않는 경우

1. **Vercel 함수 타임아웃**: 무료 플랜 10초 제한. 한 번에 10개 topic × 3개 언어 → 약 30초 예상. **Pro 플랜 (300초)** 필요.
2. **Gemini API Key 미설정**: Vercel 환경변수 `GEMINI_API_KEY` 확인, 없으면 Supabase `global_settings.sys_api_gemini` 확인.
3. **Migration 미적용**: `translation_status` 컬럼이 없으면 `isMissingColumnError`가 포착하여 조용히 실패. Step 2 migration 적용 여부 재확인.
4. **Vercel 로그 확인**: Dashboard → Functions → `api/admin/topics-queue` → `AIR-0129:` 접두사 로그 검색.

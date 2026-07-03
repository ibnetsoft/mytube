# Referral Migration Runbook (AIR-0122 ~ AIR-0124)

이 문서는 AIR-0122부터 AIR-0124까지 개발된 **Referral 2.0 및 Settlement Payout Processor** 관련 데이터베이스 마이그레이션 스크립트를 운영(Production) 데이터베이스에 안전하게 적용하기 위한 체크리스트 및 가이드입니다.

---

## 1. 적용해야 할 Migration 파일 목록
운영 DB에 순서대로 적용해야 할 마이그레이션 스크립트는 총 3개입니다.
1. `auth-web/migration_referral_2.0.sql`: 기존 회원의 `referred_by` NULL 값을 Default Sponsor로 일괄 업데이트.
2. `auth-web/migration_settlement_unique.sql`: 정산 중복 방지를 위한 `source_tx_id` + `commission_type` UNIQUE INDEX 추가.
3. `auth-web/migration_payout_rpc.sql`: 정산 금액 지급(pending → paid)을 위한 원자적 트랜잭션 DB RPC 함수(`process_referral_payout`) 생성.

---

## 2. 실행 순서
반드시 아래 순서대로 스크립트를 실행해야 합니다.
1. **[필수 조건 확인]**: Admin 화면(또는 DB)에서 Default Sponsor 설정 확인 및 중복 트랜잭션 데이터 정리
2. `migration_referral_2.0.sql` 실행
3. `migration_settlement_unique.sql` 실행
4. `migration_payout_rpc.sql` 실행
5. **[검증]**: 신규 RPC 정상 동작 및 인덱스 적용 여부 확인

---

## 3. 실행 전 필수 조건
마이그레이션 적용 전 아래 항목이 충족되지 않으면 스크립트 실행이 실패하거나 원치 않은 데이터 오염이 발생할 수 있습니다.

### 3.1. Default Sponsor 설정
`global_settings` 테이블에 `referral_default_sponsor_uuid` 값이 정상적으로 세팅되어 있어야 합니다. 이 값이 누락되면 `migration_referral_2.0.sql` 실행 시 `referred_by`가 업데이트되지 않습니다.
- **확인 방법**: Admin 대시보드의 **Settings > Referral** 메뉴에서 Default Sponsor가 지정되어 있는지 확인하세요.

### 3.2. 중복 source_tx_id 확인 (Unique Index 적용 전)
`migration_settlement_unique.sql` 스크립트는 기존 `referral_commissions` 테이블에 중복된 `(metadata->>'source_tx_id', commission_type)` 쌍이 존재하면 인덱스 생성 시 충돌(에러)이 발생합니다.
- **확인 및 정리**: 
  ```sql
  SELECT metadata->>'source_tx_id', commission_type, count(*) 
  FROM public.referral_commissions 
  WHERE metadata->>'source_tx_id' IS NOT NULL 
  GROUP BY metadata->>'source_tx_id', commission_type 
  HAVING count(*) > 1;
  ```
  위 쿼리 결과가 존재한다면, 중복된 가비지/테스트 데이터를 먼저 삭제하거나 병합(`status = 'cancelled'` 등)하여 중복을 제거해야 합니다.

---

## 4. 실행 SQL
데이터베이스 관리 툴(Supabase SQL Editor, psql 등)에서 다음 내용을 복사하여 차례대로 실행합니다.

### 4.1. migration_referral_2.0.sql
```sql
-- (해당 파일 내용을 붙여넣어 실행합니다)
DO $$
DECLARE
    v_default_uuid UUID;
BEGIN
    SELECT value INTO v_default_uuid
    FROM global_settings 
    WHERE key = 'referral_default_sponsor_uuid';

    IF v_default_uuid IS NOT NULL THEN
        UPDATE public.profiles
        SET referred_by = v_default_uuid
        WHERE referred_by IS NULL 
          AND id != v_default_uuid;
    END IF;
END $$;
```

### 4.2. migration_settlement_unique.sql
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_commissions_tx 
ON public.referral_commissions((metadata->>'source_tx_id'), commission_type) 
WHERE metadata->>'source_tx_id' IS NOT NULL;
```

### 4.3. migration_payout_rpc.sql
```sql
-- (migration_payout_rpc.sql 파일 전문을 복사하여 실행합니다)
-- CREATE OR REPLACE FUNCTION public.process_referral_payout(p_commission_id UUID) ...
```

---

## 5. 실행 후 검증 SQL
스크립트 실행 후 데이터 무결성을 검증합니다.

```sql
-- 1. Default sponsor 적용 확인: (결과가 0에 가깝거나, 최근 가입자만 나와야 함)
SELECT count(*) FROM public.profiles WHERE referred_by IS NULL;

-- 2. Unique Index 생성 여부 확인: (결과가 존재해야 함)
SELECT indexname, indexdef FROM pg_indexes WHERE indexname = 'idx_referral_commissions_tx';

-- 3. RPC 함수 생성 여부 확인: (결과가 존재해야 함)
SELECT proname FROM pg_proc WHERE proname = 'process_referral_payout';
```

---

## 6. Rollback 또는 복구 방법
- **Referral 2.0 업데이트 취소**: `migration_referral_2.0.sql`은 대규모 UPDATE를 동반합니다. 실수로 잘못된 Default Sponsor가 지정되어 롤백이 필요할 경우, 스크립트 실행 직전의 DB 스냅샷(Point-in-Time Recovery)을 활용하여 복구하는 것을 권장합니다.
- **Index 삭제**: `DROP INDEX public.idx_referral_commissions_tx;`
- **RPC 삭제**: `DROP FUNCTION public.process_referral_payout(UUID);`

---

## 7. 운영 중 주의사항
- **자동 차감(Rollback) 없음**: 이번 마이그레이션을 통해 `Approve & Pay`로 지급된 커미션(`paid`)은, 이후 고객이 결제(Recharge)를 환불하더라도 자동으로 차감(Rollback)되지 않습니다. 환불이 발생할 경우 관리자가 수동으로 금액(usdt_balance)을 조정해야 합니다.
- **수동 정산 전용**: 시스템은 현재 커미션을 오직 `pending` 상태로만 생성합니다. 자동 지급되지 않으므로 관리자가 주기적으로 접속하여 처리해야 합니다.

---

## 8. Admin에서 확인할 화면
마이그레이션이 성공적으로 완료되었다면, 관리자는 다음 두 화면을 확인해야 합니다.
1. **[Global Settings]**: `referral_mode` 및 `referral_level1_percent`, `referral_level2_percent`가 정상적으로 노출 및 저장되는지 확인.
2. **[Settlements Payout 목록]** (`/admin/settlements`): 
   - `pending`, `paid`, `cancelled` 목록이 정상 표시되는지 확인.
   - `pending` 상태의 목록 우측에만 **[Approve & Pay]** 액션 버튼이 활성화되어 있는지 확인.

---

## 9. 실제 지급(Payout) 테스트 절차
Production 환경에 반영된 후, 즉시 결제 사이클이 정상 동작하는지 테스트합니다.
1. 관리자 계정으로 사용자(테스트 계정)에게 **Recharge(결제 충전)**를 1회 발생시킵니다.
2. `/admin/settlements`에 접속하여 `pending` 상태의 정산(Level 1, Level 2) 내역이 생성되었는지 확인합니다.
3. 해당 건의 **[Approve & Pay]** 버튼을 클릭하고 `confirm` 대화창을 승인합니다.
4. 버튼이 `Processing...`으로 변경되었다가 사라지며, 상태가 `paid`로 갱신되는지 확인합니다.
5. 수혜자 계정의 Profile을 조회하여 `usdt_balance`가 해당 커미션 토큰만큼 정확히 증가했는지 확인합니다.

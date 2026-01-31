
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
// 주의: 이것은 Service Role Key여야 합니다. (Supabase 대시보드 > Project Settings > API 에서 확인)
// 하지만 일단 .env.local에 저장된 키를 사용하되, 
// 실제로는 'service_role' 키를 별도 환경변수(SUPABASE_SERVICE_ROLE_KEY)로 관리해야 
// 모든 유저 목록(auth.users)을 조회할 수 있습니다. 
// 현재 설정된 ANON_KEY로는 보안상 '내 정보'만 볼 수 있고 '남의 정보'는 못 봅니다.
// 
// 따라서, 개발자님이 .env.local에 SUPABASE_SERVICE_ROLE_KEY를 추가해주셔야 완벽하게 작동합니다.
// 일단은 코드를 작성해두겠습니다.
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
    auth: {
        autoRefreshToken: false,
        persistSession: false
    }
})

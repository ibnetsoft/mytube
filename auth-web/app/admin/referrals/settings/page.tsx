'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useAuthToken, authedFetch } from '../_hooks'
import { Card, ErrorBlock } from '../_components'

// AIR-0223: this tab intentionally does NOT reimplement the referral settings
// form. Level%/Default Sponsor/Mode/Min Payout/Cycle already have a working
// page + API (auth-web/app/admin/settings/referral) — "실제 저장 로직 변경은
// 하지 않는다. 기존 global_settings API를 사용한다" is satisfied by linking to
// it unmodified, not by duplicating it. The Country Manager section below is
// new UI only — it calls the existing /api/admin/referrals PATCH endpoint
// (make_country_manager/managed_country), which already existed and worked,
// just had no UI surfacing it.
export default function ReferralAdminSettingsPage() {
    const { token, ready } = useAuthToken()
    const [userId, setUserId] = useState('')
    const [countryCode, setCountryCode] = useState('')
    const [commissionRate, setCommissionRate] = useState('0')
    const [saving, setSaving] = useState(false)
    const [message, setMessage] = useState('')
    const [error, setError] = useState('')

    const assignCountryManager = async (makeManager: boolean) => {
        if (!userId.trim()) { setError('사용자 ID를 입력해주세요.'); return }
        setSaving(true)
        setError('')
        setMessage('')
        try {
            const res = await authedFetch(token, '/api/admin/referrals', {
                method: 'PATCH',
                body: JSON.stringify({
                    userId: userId.trim(),
                    country_code: countryCode.trim().toUpperCase(),
                    referral_country: countryCode.trim().toUpperCase(),
                    commission_rate: Number(commissionRate) || 0,
                    make_country_manager: makeManager,
                }),
            })
            const json = await res.json()
            if (json.success) setMessage(makeManager ? '국가 관리자로 지정되었습니다.' : '국가 관리자 권한이 해제되었습니다.')
            else setError(json.error || '업데이트에 실패했습니다')
        } catch (e: any) {
            setError(e.message)
        } finally {
            setSaving(false)
        }
    }

    return (
        <div className="space-y-6 max-w-2xl">
            <Card>
                <h2 className="text-lg font-bold mb-2">추천인 모드 / 요율 / 기본 스폰서</h2>
                <p className="text-sm text-gray-400 mb-4">
                    기존 설정 페이지에서 관리됩니다 — 추천인 모드, 1/2단계 요율, 기본 스폰서, 최소 출금액, 정산 주기.
                </p>
                <Link
                    href="/admin/settings/referral"
                    className="inline-block px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 text-sm font-semibold"
                >
                    추천인 설정 열기 →
                </Link>
            </Card>

            <Card>
                <h2 className="text-lg font-bold mb-2">국가 관리자</h2>
                <p className="text-sm text-gray-400 mb-4">
                    프로필의 국가를 지정하고, 선택적으로 국가 관리자 권한을 부여합니다 (해당 국가로 추천인 관리 화면 범위를 제한). 기존 <code>/api/admin/referrals</code> PATCH 엔드포인트를 사용합니다.
                </p>
                {message && <div className="mb-3 p-2 bg-green-900/40 border border-green-700 rounded text-green-200 text-sm">{message}</div>}
                {error && <div className="mb-3"><ErrorBlock message={error} /></div>}
                <div className="space-y-3">
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">사용자 ID (UUID)</label>
                        <input className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                            value={userId} onChange={e => setUserId(e.target.value)} placeholder="profiles.id" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">국가 코드</label>
                            <input className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                                value={countryCode} onChange={e => setCountryCode(e.target.value)} placeholder="KR" maxLength={2} />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">커미션 요율 (%)</label>
                            <input type="number" className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                                value={commissionRate} onChange={e => setCommissionRate(e.target.value)} />
                        </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                        <button disabled={saving || !ready} onClick={() => assignCountryManager(true)}
                            className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm font-semibold">
                            국가 관리자로 지정
                        </button>
                        <button disabled={saving || !ready} onClick={() => assignCountryManager(false)}
                            className="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-sm">
                            국가/요율만 업데이트
                        </button>
                    </div>
                    <p className="text-xs text-gray-600 pt-1">
                        참고: 이 API는 sub_admin 권한을 부여만 하고 해제하지는 않습니다 — &quot;국가/요율만 업데이트&quot;로는 기존 국가 관리자를 해제할 수 없습니다.
                    </p>
                </div>
            </Card>
        </div>
    )
}

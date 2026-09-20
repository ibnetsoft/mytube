'use client'

import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '@/lib/LanguageContext'

interface Tenant {
    tenant_key: string
    tenant_name: string
    brand_name: string
    commission_percent: number
    min_commission_usd: number
    license_tier: string
    status: 'active' | 'suspended' | 'cancelled'
    setup_fee_usd?: number
    price_per_channel_usd?: number
    max_channels?: number
    monthly_fee_usd?: number
    currency?: string
    user_count?: number
    created_at: string
}

interface TenantUser {
    tenant_key: string
    user_id: string
    role: string
    status: string
    profiles?: {
        email: string
        full_name?: string
    }
}

interface TenantApplication {
    id: string
    company_name: string
    brand_name?: string
    contact_name: string
    email: string
    phone: string
    channel_count: number
    estimated_setup_fee: number
    estimated_monthly_fee: number
    currency: string
    notes?: string
    status: 'pending' | 'approved' | 'rejected'
    tenant_key?: string
    created_at: string
}

interface TenantManagementProps {
    authToken: string
    isSuperAdmin: boolean
}

export default function TenantManagement({ authToken, isSuperAdmin }: TenantManagementProps) {
    const { language } = useLanguage()
    const isKor = language === 'ko'

    // 서브 탭: 'tenants' (테넌트 목록) | 'applications' (도입 신청서)
    const [subTab, setSubTab] = useState<'tenants' | 'applications'>('tenants')

    const [tenants, setTenants] = useState<Tenant[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedTenant, setSelectedTenant] = useState<string | null>(null)
    const [tenantUsers, setTenantUsers] = useState<TenantUser[]>([])

    // 신청서 상태
    const [applications, setApplications] = useState<TenantApplication[]>([])
    const [appLoading, setAppLoading] = useState(false)
    const [approvingId, setApprovingId] = useState<string | null>(null)

    // 새 테넌트 생성 폼 (세팅비 + 채널당 구독료 모델)
    const [showCreate, setShowCreate] = useState(false)
    const [createForm, setCreateForm] = useState({
        tenant_key: '',
        tenant_name: '',
        brand_name: '',
        setup_fee_usd: 500,
        price_per_channel_usd: 100,
        max_channels: 5,
        currency: 'USD',
        commission_percent: 0,
        min_commission_usd: 0,
        license_tier: 'standard'
    })

    // 편집 폼
    const [showEdit, setShowEdit] = useState(false)
    const [editForm, setEditForm] = useState({
        setup_fee_usd: 0,
        price_per_channel_usd: 0,
        max_channels: 5,
        monthly_fee_usd: 0,
        currency: 'USD',
        license_tier: 'standard',
        commission_percent: 0,
        min_commission_usd: 0,
        brand_name: '',
        primary_color: '',
        status: 'active' as 'active' | 'suspended' | 'cancelled',
        watermark_enabled: true
    })

    const adminFetch = useCallback(async (input: RequestInfo | URL, init: RequestInit = {}) => {
        const headers = new Headers(init.headers || {})
        if (authToken) headers.set('Authorization', `Bearer ${authToken}`)
        return fetch(input, { ...init, headers })
    }, [authToken])

    // 테넌트 목록 불러오기
    const fetchTenants = useCallback(async () => {
        setLoading(true)
        try {
            const res = await adminFetch('/api/admin/tenants')
            const data = await res.json()
            if (res.ok) {
                setTenants(data.tenants || [])
            }
        } catch (e) {
            console.error('Failed to fetch tenants:', e)
        } finally {
            setLoading(false)
        }
    }, [adminFetch])

    // 도입 신청서 목록 불러오기
    const fetchApplications = useCallback(async () => {
        setAppLoading(true)
        try {
            const res = await adminFetch('/api/admin/tenant-applications')
            const data = await res.json()
            if (res.ok) {
                setApplications(data.applications || [])
            }
        } catch (e) {
            console.error('Failed to fetch applications:', e)
        } finally {
            setAppLoading(false)
        }
    }, [adminFetch])

    // 신청서 승인 및 테넌트 자동 생성
    const handleApproveApplication = async (app: TenantApplication) => {
        const confirmMsg = isKor
            ? `[${app.company_name}] 신청서를 승인하고 정식 테넌트로 자동 생성하시겠습니까?\n\n- 희망 채널: ${app.channel_count}개\n- 세팅비: $${app.estimated_setup_fee}\n- 월 구독료: $${app.estimated_monthly_fee}`
            : `Approve [${app.company_name}] and auto-create tenant?`

        if (!confirm(confirmMsg)) return

        setApprovingId(app.id)
        try {
            const res = await adminFetch(`/api/admin/tenant-applications/${app.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    max_channels: app.channel_count,
                    setup_fee_usd: app.estimated_setup_fee,
                    price_per_channel_usd: 100,
                    license_tier: 'business'
                })
            })
            const data = await res.json()
            if (res.ok && data.success) {
                alert(isKor ? `✅ 테넌트 [${data.tenant_key}]가 성공적으로 자동 생성 및 승인되었습니다!` : 'Tenant approved successfully!')
                fetchApplications()
                fetchTenants()
            } else {
                alert((isKor ? '승인 실패: ' : 'Approval failed: ') + (data.error || ''))
            }
        } catch (e: any) {
            alert((isKor ? '오류: ' : 'Error: ') + (e.message || String(e)))
        } finally {
            setApprovingId(null)
        }
    }

    // 신청서 반려
    const handleRejectApplication = async (appId: string) => {
        if (!confirm(isKor ? '이 신청서를 반려 처리하시겠습니까?' : 'Reject this application?')) return

        try {
            const res = await adminFetch(`/api/admin/tenant-applications/${appId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'rejected' })
            })
            const data = await res.json()
            if (res.ok && data.success) {
                alert(isKor ? '신청서가 반려 처리되었습니다.' : 'Application rejected.')
                fetchApplications()
            } else {
                alert((isKor ? '반려 실패: ' : 'Rejection failed: ') + (data.error || ''))
            }
        } catch (e: any) {
            alert((isKor ? '오류: ' : 'Error: ') + (e.message || String(e)))
        }
    }

    // 테넌트 사용자 목록 불러오기
    const fetchTenantUsers = async (tenantKey: string) => {
        try {
            const res = await adminFetch(`/api/admin/tenants/${tenantKey}`)
            const data = await res.json()
            if (res.ok) {
                setTenantUsers(data.users || [])
            }
        } catch (e) {
            console.error('Failed to fetch tenant users:', e)
        }
    }

    // 테넌트 생성
    const handleCreateTenant = async () => {
        if (!createForm.tenant_key || !createForm.tenant_name) {
            alert(isKor ? '테넌트 키와 이름은 필수입니다.' : 'Tenant key and name are required.')
            return
        }

        try {
            const res = await adminFetch('/api/admin/tenants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(createForm)
            })
            const data = await res.json()
            if (res.ok) {
                alert(isKor ? '테넌트가 생성되었습니다.' : 'Tenant created successfully.')
                setShowCreate(false)
                setCreateForm({
                    tenant_key: '',
                    tenant_name: '',
                    brand_name: '',
                    setup_fee_usd: 500,
                    price_per_channel_usd: 100,
                    max_channels: 5,
                    currency: 'USD',
                    commission_percent: 0,
                    min_commission_usd: 0,
                    license_tier: 'standard'
                })
                fetchTenants()
            } else {
                alert((isKor ? '생성 실패: ' : 'Creation failed: ') + (data.error || ''))
            }
        } catch (e) {
            alert((isKor ? '오류: ' : 'Error: ') + String(e))
        }
    }

    // 테넌트 업데이트
    const handleUpdateTenant = async (tenantKey: string) => {
        try {
            const res = await adminFetch(`/api/admin/tenants/${tenantKey}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(editForm)
            })
            const data = await res.json()
            if (res.ok) {
                alert(isKor ? '테넌트가 업데이트되었습니다.' : 'Tenant updated successfully.')
                setShowEdit(false)
                fetchTenants()
            } else {
                alert((isKor ? '업데이트 실패: ' : 'Update failed: ') + (data.error || ''))
            }
        } catch (e) {
            alert((isKor ? '오류: ' : 'Error: ') + String(e))
        }
    }

    // 테넌트 삭제
    const handleDeleteTenant = async (tenantKey: string) => {
        if (tenantKey === 'default') {
            alert(isKor ? '기본 테넌트는 삭제할 수 없습니다.' : 'Cannot delete default tenant.')
            return
        }
        if (!confirm(isKor ? '정말 이 테넌트를 삭제하시겠습니까?' : 'Are you sure you want to delete this tenant?')) {
            return
        }

        try {
            const res = await adminFetch(`/api/admin/tenants/${tenantKey}`, {
                method: 'DELETE'
            })
            if (res.ok) {
                alert(isKor ? '테넌트가 삭제되었습니다.' : 'Tenant deleted successfully.')
                if (selectedTenant === tenantKey) {
                    setSelectedTenant(null)
                    setTenantUsers([])
                }
                fetchTenants()
            } else {
                alert(isKor ? '삭제 실패' : 'Delete failed')
            }
        } catch (e) {
            alert(isKor ? '오류: ' : 'Error: ' + String(e))
        }
    }

    // 편집 모달 열기
    const openEdit = (tenant: Tenant) => {
        setEditForm({
            setup_fee_usd: tenant.setup_fee_usd || 0,
            price_per_channel_usd: tenant.price_per_channel_usd || 0,
            max_channels: tenant.max_channels || 5,
            monthly_fee_usd: tenant.monthly_fee_usd || ((tenant.price_per_channel_usd || 0) * (tenant.max_channels || 5)),
            currency: tenant.currency || 'USD',
            license_tier: tenant.license_tier || 'standard',
            commission_percent: tenant.commission_percent,
            min_commission_usd: tenant.min_commission_usd,
            brand_name: tenant.brand_name || '',
            primary_color: '',
            status: tenant.status,
            watermark_enabled: true
        })
        setSelectedTenant(tenant.tenant_key)
        setShowEdit(true)
    }

    useEffect(() => {
        if (isSuperAdmin) {
            fetchTenants()
            fetchApplications()
        }
    }, [isSuperAdmin, fetchTenants, fetchApplications])

    if (!isSuperAdmin) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <div className="text-2xl mb-2">🔒</div>
                    <div className="text-gray-500">{isKor ? '접근 권한이 없습니다.' : 'Access denied'}</div>
                </div>
            </div>
        )
    }

    const pendingAppsCount = applications.filter(a => a.status === 'pending').length

    return (
        <div className="space-y-6">
            {/* 헤더 */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-black text-white">
                        {isKor ? '🏢 테넌트 & B2B 온보딩 관리' : '🏢 Tenant & B2B Onboarding'}
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">
                        {isKor ? '세팅비, 채널당 구독료 및 B2B 도입 신청서 검토·승인' : 'Setup fee, per-channel subscription & B2B application approvals'}
                    </p>
                </div>
                {subTab === 'tenants' && (
                    <button
                        onClick={() => setShowCreate(true)}
                        className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all shadow-lg shadow-blue-500/20"
                    >
                        {isKor ? '+ 새 테넌트 직접 등록' : '+ New Tenant'}
                    </button>
                )}
            </div>

            {/* 서브 탭: 등록 테넌트 vs 도입 신청서 */}
            <div className="flex gap-2 border-b border-white/10 pb-3">
                <button
                    onClick={() => setSubTab('tenants')}
                    className={`px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 ${
                        subTab === 'tenants'
                            ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                            : 'bg-white/5 text-gray-400 hover:text-white hover:bg-white/10'
                    }`}
                >
                    <span>🏢 등록된 테넌트 목록</span>
                    <span className="bg-black/30 px-2 py-0.5 rounded-full text-[10px]">{tenants.length}</span>
                </button>
                <button
                    onClick={() => setSubTab('applications')}
                    className={`px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 ${
                        subTab === 'applications'
                            ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                            : 'bg-white/5 text-gray-400 hover:text-white hover:bg-white/10'
                    }`}
                >
                    <span>📩 B2B 도입 신청서</span>
                    {pendingAppsCount > 0 ? (
                        <span className="bg-amber-400 text-black px-2 py-0.5 rounded-full text-[10px] font-black animate-pulse">
                            {pendingAppsCount}건 검토대기
                        </span>
                    ) : (
                        <span className="bg-white/10 text-gray-400 px-2 py-0.5 rounded-full text-[10px]">
                            {applications.length}건
                        </span>
                    )}
                </button>
            </div>

            {subTab === 'applications' ? (
                /* B2B 도입 신청서 목록 화면 */
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-base font-black text-white flex items-center gap-2">
                            <span>신청서 접수 내역</span>
                            <span className="text-xs font-normal text-gray-400">
                                (세팅비 입금 확인 후 [승인]을 클릭하면 테넌트가 자동 생성됩니다)
                            </span>
                        </h2>
                        <button
                            onClick={fetchApplications}
                            disabled={appLoading}
                            className="px-3 py-1.5 bg-white/5 hover:bg-white/10 text-gray-300 text-xs rounded-lg transition-all"
                        >
                            {appLoading ? '새로고침 중...' : '새로고침 ↻'}
                        </button>
                    </div>

                    <div className="bg-[#0f172a]/40 border border-white/10 rounded-2xl overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead>
                                    <tr className="border-b border-white/10 text-left">
                                        <th className="px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">회사 / 브랜드</th>
                                        <th className="px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">담당자</th>
                                        <th className="px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">연락처 / 이메일</th>
                                        <th className="px-4 py-3 text-center text-[10px] text-gray-500 font-black uppercase tracking-widest">희망 채널</th>
                                        <th className="px-4 py-3 text-right text-[10px] text-gray-500 font-black uppercase tracking-widest">예상 세팅비</th>
                                        <th className="px-4 py-3 text-right text-[10px] text-gray-500 font-black uppercase tracking-widest">예상 월 구독료</th>
                                        <th className="px-4 py-3 text-center text-[10px] text-gray-500 font-black uppercase tracking-widest">상태</th>
                                        <th className="px-4 py-3 text-center text-[10px] text-gray-500 font-black uppercase tracking-widest">접수일시</th>
                                        <th className="px-4 py-3 text-center text-[10px] text-gray-500 font-black uppercase tracking-widest">승인 / 관리</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {appLoading ? (
                                        <tr>
                                            <td colSpan={9} className="text-center py-10 text-gray-500">
                                                신청서를 불러오는 중입니다...
                                            </td>
                                        </tr>
                                    ) : applications.length === 0 ? (
                                        <tr>
                                            <td colSpan={9} className="text-center py-12 text-gray-500">
                                                접수된 B2B 도입 신청서가 없습니다.
                                            </td>
                                        </tr>
                                    ) : (
                                        applications.map(app => {
                                            const isPending = app.status === 'pending'
                                            const isApproved = app.status === 'approved'
                                            const isRejected = app.status === 'rejected'
                                            return (
                                                <tr key={app.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                                                    <td className="px-4 py-3">
                                                        <div className="font-black text-white text-sm">{app.company_name}</div>
                                                        {app.brand_name && app.brand_name !== app.company_name && (
                                                            <div className="text-[11px] text-gray-400">브랜드: {app.brand_name}</div>
                                                        )}
                                                        {app.notes && (
                                                            <div className="text-[10px] text-blue-300/80 mt-1 max-w-xs truncate" title={app.notes}>
                                                                💬 {app.notes}
                                                            </div>
                                                        )}
                                                    </td>
                                                    <td className="px-4 py-3 text-sm text-gray-200 font-medium">
                                                        {app.contact_name}
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="text-xs text-white font-mono">{app.phone}</div>
                                                        <div className="text-[11px] text-gray-400 font-mono">{app.email}</div>
                                                    </td>
                                                    <td className="px-4 py-3 text-center">
                                                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-black bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                                            {app.channel_count}개 채널
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-3 text-right font-bold text-emerald-400 text-sm">
                                                        ${(app.estimated_setup_fee || 500).toLocaleString()}
                                                    </td>
                                                    <td className="px-4 py-3 text-right font-bold text-blue-400 text-sm">
                                                        ${(app.estimated_monthly_fee || (app.channel_count * 100)).toLocaleString()}
                                                        <span className="text-[10px] text-gray-400 block font-normal">/월</span>
                                                    </td>
                                                    <td className="px-4 py-3 text-center">
                                                        {isPending && (
                                                            <span className="px-2.5 py-1 rounded-full text-[10px] font-black bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                                                검토 대기
                                                            </span>
                                                        )}
                                                        {isApproved && (
                                                            <div className="space-y-0.5">
                                                                <span className="px-2.5 py-1 rounded-full text-[10px] font-black bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 block">
                                                                    승인 완료
                                                                </span>
                                                                {app.tenant_key && (
                                                                    <span className="text-[9px] text-gray-400 block font-mono">
                                                                        [{app.tenant_key}]
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}
                                                        {isRejected && (
                                                            <span className="px-2.5 py-1 rounded-full text-[10px] font-black bg-red-500/20 text-red-300 border border-red-500/30">
                                                                반려됨
                                                            </span>
                                                        )}
                                                    </td>
                                                    <td className="px-4 py-3 text-center text-gray-400 text-xs">
                                                        {new Date(app.created_at).toLocaleDateString()}
                                                    </td>
                                                    <td className="px-4 py-3 text-center">
                                                        {isPending ? (
                                                            <div className="flex gap-2 justify-center">
                                                                <button
                                                                    onClick={() => handleApproveApplication(app)}
                                                                    disabled={approvingId === app.id}
                                                                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-[11px] font-black rounded-lg transition-all shadow-md shadow-emerald-600/20"
                                                                >
                                                                    {approvingId === app.id ? '생성 중...' : '✓ 승인(테넌트 생성)'}
                                                                </button>
                                                                <button
                                                                    onClick={() => handleRejectApplication(app.id)}
                                                                    className="px-2.5 py-1.5 bg-white/5 hover:bg-red-500/20 hover:text-red-300 text-gray-400 text-[11px] font-black rounded-lg transition-all"
                                                                >
                                                                    반려
                                                                </button>
                                                            </div>
                                                        ) : isApproved ? (
                                                            <button
                                                                onClick={() => {
                                                                    if (app.tenant_key) {
                                                                        setSubTab('tenants')
                                                                        setSelectedTenant(app.tenant_key)
                                                                        fetchTenantUsers(app.tenant_key)
                                                                    }
                                                                }}
                                                                className="text-xs text-blue-400 hover:underline font-bold"
                                                            >
                                                                테넌트 확인 →
                                                            </button>
                                                        ) : (
                                                            <span className="text-gray-600 text-xs">-</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            )
                                        })
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            ) : (
                /* 기존 테넌트 목록 화면 */
                <>

            {/* 통계 카드 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">총 테넌트 (활성)</div>
                    <div className="text-2xl font-black text-white mt-1">
                        {tenants.filter(t => t.status === 'active').length} <span className="text-sm text-gray-500 font-normal">/ {tenants.length}</span>
                    </div>
                </div>
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">총 세팅비 매출</div>
                    <div className="text-2xl font-black text-emerald-400 mt-1">
                        ${tenants.reduce((acc, t) => acc + (t.setup_fee_usd || 0), 0).toLocaleString()}
                    </div>
                </div>
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">예상 월 구독 매출 (MRR)</div>
                    <div className="text-2xl font-black text-blue-400 mt-1">
                        ${tenants.reduce((acc, t) => {
                            const fee = t.monthly_fee_usd !== undefined ? t.monthly_fee_usd : ((t.price_per_channel_usd || 0) * (t.max_channels || 5))
                            return acc + fee
                        }, 0).toLocaleString()}
                        <span className="text-xs text-gray-400 font-normal ml-1">/월</span>
                    </div>
                </div>
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">총 운영 가능 채널</div>
                    <div className="text-2xl font-black text-purple-400 mt-1">
                        {tenants.reduce((acc, t) => acc + (t.max_channels || 5), 0)}
                        <span className="text-sm text-gray-400 font-normal ml-1">채널 (최대)</span>
                    </div>
                </div>
            </div>

            {/* 테넌트 목록 */}
            <div className="bg-[#0f172a]/40 border border-white/10 rounded-2xl overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-white/10">
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">테넌트 키</th>
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">브랜드</th>
                                <th className="text-right px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">초기 세팅비</th>
                                <th className="text-right px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">채널당 단가</th>
                                <th className="text-center px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">최대 채널</th>
                                <th className="text-right px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">예상 월 구독료</th>
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">티어</th>
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">상태</th>
                                <th className="text-center px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">사용자</th>
                                <th className="text-center px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">작업</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={10} className="text-center py-8 text-gray-500">
                                        {isKor ? '로딩 중...' : 'Loading...'}
                                    </td>
                                </tr>
                            ) : tenants.length === 0 ? (
                                <tr>
                                    <td colSpan={10} className="text-center py-8 text-gray-500">
                                        {isKor ? '테넌트가 없습니다.' : 'No tenants found.'}
                                    </td>
                                </tr>
                            ) : (
                                tenants.map(tenant => {
                                    const maxCh = tenant.max_channels || 5
                                    const pricePerCh = tenant.price_per_channel_usd || 0
                                    const estMonthly = tenant.monthly_fee_usd !== undefined ? tenant.monthly_fee_usd : (pricePerCh * maxCh)
                                    const curr = tenant.currency === 'KRW' ? '₩' : '$'
                                    return (
                                        <tr key={tenant.tenant_key} className="border-b border-white/5 hover:bg-white/5">
                                            <td className="px-4 py-3">
                                                <div className="font-black text-white">{tenant.tenant_key}</div>
                                                {tenant.tenant_key === 'default' && (
                                                    <span className="text-[9px] text-blue-400">기본</span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-white font-medium">{tenant.brand_name || tenant.tenant_name}</td>
                                            <td className="px-4 py-3 text-right">
                                                <span className="font-bold text-emerald-400">
                                                    {curr}{(tenant.setup_fee_usd || 0).toLocaleString()}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-right">
                                                <span className="font-bold text-blue-400">
                                                    {curr}{pricePerCh.toLocaleString()}
                                                </span>
                                                <span className="text-[10px] text-gray-400 block">/채널/월</span>
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-black bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                                    최대 {maxCh}개
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-right">
                                                <span className="font-black text-white text-sm">
                                                    {curr}{estMonthly.toLocaleString()}
                                                </span>
                                                <span className="text-[10px] text-gray-500 block">월 청구액</span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`text-[10px] px-2 py-1 rounded-full ${
                                                    tenant.license_tier === 'enterprise' ? 'bg-purple-500/20 text-purple-400' :
                                                    tenant.license_tier === 'business' ? 'bg-blue-500/20 text-blue-400' :
                                                    tenant.license_tier === 'starter' ? 'bg-gray-500/20 text-gray-400' :
                                                    'bg-green-500/20 text-green-400'
                                                }`}>
                                                    {tenant.license_tier.toUpperCase()}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`text-[10px] px-2 py-1 rounded-full ${
                                                    tenant.status === 'active' ? 'bg-green-500/20 text-green-400' :
                                                    tenant.status === 'suspended' ? 'bg-orange-500/20 text-orange-400' :
                                                    'bg-red-500/20 text-red-400'
                                                }`}>
                                                    {tenant.status.toUpperCase()}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-center text-white font-medium">
                                                {tenant.user_count || 0}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex gap-2 justify-center">
                                                    <button
                                                        onClick={() => openEdit(tenant)}
                                                        className="px-3 py-1 bg-white/5 hover:bg-white/10 text-white text-[10px] font-black rounded-lg transition-all"
                                                    >
                                                        {isKor ? '설정' : 'Edit'}
                                                    </button>
                                                    <button
                                                        onClick={() => {
                                                            setSelectedTenant(tenant.tenant_key)
                                                            fetchTenantUsers(tenant.tenant_key)
                                                        }}
                                                        className="px-3 py-1 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-[10px] font-black rounded-lg transition-all"
                                                    >
                                                        {isKor ? '사용자' : 'Users'}
                                                    </button>
                                                    {tenant.tenant_key !== 'default' && (
                                                        <button
                                                            onClick={() => handleDeleteTenant(tenant.tenant_key)}
                                                            className="px-3 py-1 bg-red-500/10 hover:bg-red-500/20 text-red-400 text-[10px] font-black rounded-lg transition-all"
                                                        >
                                                            {isKor ? '삭제' : 'Delete'}
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    )
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* 선택한 테넌트의 사용자 목록 */}
            {selectedTenant && (
                <div className="bg-[#0f172a]/40 border border-white/10 rounded-2xl p-6">
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <h2 className="text-lg font-black text-white">
                                {selectedTenant} {isKor ? '사용자 목록' : 'Users'}
                            </h2>
                        </div>
                        <button
                            onClick={() => {
                                setSelectedTenant(null)
                                setTenantUsers([])
                            }}
                            className="text-gray-500 hover:text-white text-sm"
                        >
                            {isKor ? '닫기' : 'Close'}
                        </button>
                    </div>
                    {tenantUsers.length === 0 ? (
                        <div className="text-center py-4 text-gray-500">
                            {isKor ? '사용자가 없습니다.' : 'No users found.'}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {tenantUsers.map(user => (
                                <div key={user.user_id} className="bg-white/5 border border-white/10 rounded-xl p-4">
                                    <div className="text-sm font-black text-white mb-1">
                                        {user.profiles?.email || user.user_id.slice(0, 8) + '...'}
                                    </div>
                                    <div className="flex gap-2 mt-2">
                                        <span className="text-[10px] px-2 py-1 bg-blue-500/10 text-blue-400 rounded-full">
                                            {user.role}
                                        </span>
                                        <span className={`text-[10px] px-2 py-1 rounded-full ${
                                            user.status === 'active' ? 'bg-green-500/10 text-green-400' : 'bg-gray-500/10 text-gray-400'
                                        }`}>
                                            {user.status}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
            </>
            )}

            {/* 새 테넌트 생성 모달 */}
            {showCreate && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto" onClick={() => setShowCreate(false)}>
                    <div className="bg-[#0f172a] border border-white/20 rounded-2xl p-6 w-full max-w-lg my-8 shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <div>
                                <h2 className="text-lg font-black text-white">
                                    {isKor ? '🏢 새 테넌트 등록 (구독 요금제 세팅)' : '🏢 Create New Tenant (Subscription Plan)'}
                                </h2>
                                <p className="text-xs text-gray-400 mt-0.5">
                                    {isKor ? '세팅비와 채널당 월 구독료(최대 5채널)를 설정합니다.' : 'Set initial setup fee and per-channel subscription fee (max 5).'}
                                </p>
                            </div>
                            <button onClick={() => setShowCreate(false)} className="text-gray-500 hover:text-white text-sm">✕</button>
                        </div>

                        <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
                            {/* 기본 정보 */}
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                        {isKor ? '테넌트 키 (고유 식별자)' : 'Tenant Key'} <span className="text-red-400">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={createForm.tenant_key}
                                        onChange={e => setCreateForm({ ...createForm, tenant_key: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '') })}
                                        placeholder="tenant-company"
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                        {isKor ? '회사/고객사 이름' : 'Tenant Name'} <span className="text-red-400">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={createForm.tenant_name}
                                        onChange={e => setCreateForm({ ...createForm, tenant_name: e.target.value })}
                                        placeholder="주식회사 에이비씨"
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '브랜드 이름 (시스템 및 워터마크 노출용)' : 'Brand Name'}
                                </label>
                                <input
                                    type="text"
                                    value={createForm.brand_name}
                                    onChange={e => setCreateForm({ ...createForm, brand_name: e.target.value })}
                                    placeholder="ABC Studio"
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
                                />
                            </div>

                            {/* 비즈니스 요금제 박스 */}
                            <div className="bg-blue-950/30 border border-blue-500/30 rounded-2xl p-4 space-y-3">
                                <div className="flex items-center justify-between">
                                    <span className="text-xs font-black text-blue-300 uppercase tracking-wider flex items-center gap-1.5">
                                        💳 세팅비 & 채널 구독 요금 설계
                                    </span>
                                    <select
                                        value={createForm.currency}
                                        onChange={e => setCreateForm({ ...createForm, currency: e.target.value })}
                                        className="bg-black/40 border border-blue-500/30 rounded-lg px-2 py-1 text-xs text-blue-200 focus:outline-none"
                                    >
                                        <option value="USD">USD ($)</option>
                                        <option value="KRW">KRW (₩)</option>
                                    </select>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    <div>
                                        <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                            초기 세팅비
                                        </label>
                                        <div className="relative">
                                            <span className="absolute left-3 top-2.5 text-xs text-gray-400">
                                                {createForm.currency === 'KRW' ? '₩' : '$'}
                                            </span>
                                            <input
                                                type="number"
                                                min="0"
                                                step="10"
                                                value={createForm.setup_fee_usd}
                                                onChange={e => setCreateForm({ ...createForm, setup_fee_usd: Number(e.target.value) })}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl pl-7 pr-3 py-2 text-white font-bold text-sm focus:outline-none focus:border-blue-500"
                                            />
                                        </div>
                                    </div>

                                    <div>
                                        <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                            채널 1개당 월 요금
                                        </label>
                                        <div className="relative">
                                            <span className="absolute left-3 top-2.5 text-xs text-gray-400">
                                                {createForm.currency === 'KRW' ? '₩' : '$'}
                                            </span>
                                            <input
                                                type="number"
                                                min="0"
                                                step="10"
                                                value={createForm.price_per_channel_usd}
                                                onChange={e => setCreateForm({ ...createForm, price_per_channel_usd: Number(e.target.value) })}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl pl-7 pr-3 py-2 text-white font-bold text-sm focus:outline-none focus:border-blue-500"
                                            />
                                        </div>
                                    </div>

                                    <div>
                                        <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                            최대 채널 수 (한도)
                                        </label>
                                        <div className="relative">
                                            <input
                                                type="number"
                                                min="1"
                                                max="20"
                                                value={createForm.max_channels}
                                                onChange={e => setCreateForm({ ...createForm, max_channels: Number(e.target.value) })}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white font-bold text-sm focus:outline-none focus:border-blue-500"
                                            />
                                            <span className="absolute right-3 top-2.5 text-xs text-gray-400">채널</span>
                                        </div>
                                    </div>
                                </div>

                                {/* 실시간 견적 요약 카드 */}
                                <div className="bg-black/50 border border-white/10 rounded-xl p-3 flex items-center justify-between">
                                    <div>
                                        <div className="text-[10px] text-gray-400">예상 고객 청구 견적</div>
                                        <div className="text-xs text-white mt-0.5">
                                            초기 <span className="font-bold text-emerald-400">{createForm.currency === 'KRW' ? '₩' : '$'}{createForm.setup_fee_usd.toLocaleString()}</span>
                                            {' + '}
                                            매월 <span className="font-bold text-blue-400">{createForm.currency === 'KRW' ? '₩' : '$'}{(createForm.price_per_channel_usd * createForm.max_channels).toLocaleString()}</span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <span className="text-[10px] text-purple-300 bg-purple-500/20 px-2 py-0.5 rounded-full border border-purple-500/30">
                                            최대 {createForm.max_channels}개 채널 풀가동 기준
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* 라이선스 티어 */}
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                        {isKor ? '라이선스 티어' : 'License Tier'}
                                    </label>
                                    <select
                                        value={createForm.license_tier}
                                        onChange={e => setCreateForm({ ...createForm, license_tier: e.target.value })}
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 cursor-pointer"
                                    >
                                        <option value="starter">Starter (기본)</option>
                                        <option value="standard">Standard (스탠다드)</option>
                                        <option value="business">Business (비즈니스 - 5채널 권장)</option>
                                        <option value="enterprise">Enterprise (엔터프라이즈)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                        {isKor ? '플랫폼 수수료율 (%) (선택)' : 'Platform Commission (%)'}
                                    </label>
                                    <input
                                        type="number"
                                        min="0"
                                        max="100"
                                        step="0.5"
                                        value={createForm.commission_percent}
                                        onChange={e => setCreateForm({ ...createForm, commission_percent: Number(e.target.value) })}
                                        placeholder="0"
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="flex gap-3 mt-6 pt-4 border-t border-white/10">
                            <button
                                onClick={handleCreateTenant}
                                className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all shadow-lg shadow-blue-500/20"
                            >
                                {isKor ? '테넌트 등록 완료' : 'Create Tenant'}
                            </button>
                            <button
                                onClick={() => setShowCreate(false)}
                                className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all"
                            >
                                {isKor ? '취소' : 'Cancel'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* 테넌트 설정 편집 모달 */}
            {showEdit && selectedTenant && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto" onClick={() => setShowEdit(false)}>
                    <div className="bg-[#0f172a] border border-white/20 rounded-2xl p-6 w-full max-w-lg my-8 shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <div>
                                <h2 className="text-lg font-black text-white">
                                    {isKor ? '⚙️ 테넌트 설정 및 요금 변경' : '⚙️ Tenant Settings & Pricing'}
                                </h2>
                                <p className="text-xs text-gray-400 mt-0.5">
                                    [{selectedTenant}] {isKor ? '테넌트의 요금 및 채널 한도를 수정합니다.' : 'Update pricing and channel limits.'}
                                </p>
                            </div>
                            <button onClick={() => setShowEdit(false)} className="text-gray-500 hover:text-white text-sm">✕</button>
                        </div>

                        <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
                            <div>
                                <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '브랜드 이름' : 'Brand Name'}
                                </label>
                                <input
                                    type="text"
                                    value={editForm.brand_name}
                                    onChange={e => setEditForm({ ...editForm, brand_name: e.target.value })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
                                />
                            </div>

                            {/* 요금제 수정 박스 */}
                            <div className="bg-blue-950/30 border border-blue-500/30 rounded-2xl p-4 space-y-3">
                                <div className="text-xs font-black text-blue-300 uppercase tracking-wider">
                                    💳 세팅비 & 채널 구독료 변경
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    <div>
                                        <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                            세팅비 ({editForm.currency})
                                        </label>
                                        <input
                                            type="number"
                                            min="0"
                                            value={editForm.setup_fee_usd}
                                            onChange={e => setEditForm({ ...editForm, setup_fee_usd: Number(e.target.value) })}
                                            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white font-bold text-sm focus:outline-none focus:border-blue-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                            채널당 월 단가
                                        </label>
                                        <input
                                            type="number"
                                            min="0"
                                            value={editForm.price_per_channel_usd}
                                            onChange={e => {
                                                const p = Number(e.target.value)
                                                setEditForm({
                                                    ...editForm,
                                                    price_per_channel_usd: p,
                                                    monthly_fee_usd: p * (editForm.max_channels || 5)
                                                })
                                            }}
                                            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white font-bold text-sm focus:outline-none focus:border-blue-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                            최대 채널 수
                                        </label>
                                        <input
                                            type="number"
                                            min="1"
                                            max="20"
                                            value={editForm.max_channels}
                                            onChange={e => {
                                                const m = Number(e.target.value)
                                                setEditForm({
                                                    ...editForm,
                                                    max_channels: m,
                                                    monthly_fee_usd: (editForm.price_per_channel_usd || 0) * m
                                                })
                                            }}
                                            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white font-bold text-sm focus:outline-none focus:border-blue-500"
                                        />
                                    </div>
                                </div>
                                <div className="text-xs text-gray-300 pt-1 flex justify-between items-center">
                                    <span>월 구독 청구액 (자동 산출):</span>
                                    <span className="font-bold text-white text-sm">
                                        {editForm.currency === 'KRW' ? '₩' : '$'}{(editForm.monthly_fee_usd || 0).toLocaleString()} / 월
                                    </span>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                        {isKor ? '테넌트 상태' : 'Status'}
                                    </label>
                                    <select
                                        value={editForm.status}
                                        onChange={e => setEditForm({ ...editForm, status: e.target.value as any })}
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 cursor-pointer"
                                    >
                                        <option value="active">Active (정상 운영)</option>
                                        <option value="suspended">Suspended (구독 일시중지/미납)</option>
                                        <option value="cancelled">Cancelled (계약 해지)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] text-gray-400 font-black uppercase tracking-widest block mb-1">
                                        {isKor ? '라이선스 티어' : 'License Tier'}
                                    </label>
                                    <select
                                        value={editForm.license_tier}
                                        onChange={e => setEditForm({ ...editForm, license_tier: e.target.value })}
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 cursor-pointer"
                                    >
                                        <option value="starter">Starter</option>
                                        <option value="standard">Standard</option>
                                        <option value="business">Business (5채널 권장)</option>
                                        <option value="enterprise">Enterprise</option>
                                    </select>
                                </div>
                            </div>

                            <div className="flex items-center gap-3 pt-2">
                                <input
                                    type="checkbox"
                                    id="watermark-enabled"
                                    checked={editForm.watermark_enabled}
                                    onChange={e => setEditForm({ ...editForm, watermark_enabled: e.target.checked })}
                                    className="w-4 h-4 accent-blue-500 cursor-pointer"
                                />
                                <label htmlFor="watermark-enabled" className="text-sm text-white cursor-pointer">
                                    {isKor ? '테넌트 전용 워터마크 자동 삽입 활성화' : 'Enable Tenant Watermark'}
                                </label>
                            </div>
                        </div>

                        <div className="flex gap-3 mt-6 pt-4 border-t border-white/10">
                            <button
                                onClick={() => handleUpdateTenant(selectedTenant)}
                                className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all shadow-lg shadow-blue-500/20"
                            >
                                {isKor ? '설정 저장' : 'Save Changes'}
                            </button>
                            <button
                                onClick={() => setShowEdit(false)}
                                className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all"
                            >
                                {isKor ? '취소' : 'Cancel'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
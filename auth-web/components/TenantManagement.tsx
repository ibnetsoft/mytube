'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/lib/LanguageContext'

interface Tenant {
    tenant_key: string
    tenant_name: string
    brand_name: string
    commission_percent: number
    min_commission_usd: number
    license_tier: string
    status: 'active' | 'suspended' | 'cancelled'
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

interface TenantManagementProps {
    authToken: string
    isSuperAdmin: boolean
}

export default function TenantManagement({ authToken, isSuperAdmin }: TenantManagementProps) {
    const { language } = useLanguage()
    const isKor = language === 'ko'

    const [tenants, setTenants] = useState<Tenant[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedTenant, setSelectedTenant] = useState<string | null>(null)
    const [tenantUsers, setTenantUsers] = useState<TenantUser[]>([])

    // 새 테넌트 생성 폼
    const [showCreate, setShowCreate] = useState(false)
    const [createForm, setCreateForm] = useState({
        tenant_key: '',
        tenant_name: '',
        brand_name: '',
        commission_percent: 10,
        min_commission_usd: 0,
        license_tier: 'standard'
    })

    // 편집 폼
    const [showEdit, setShowEdit] = useState(false)
    const [editForm, setEditForm] = useState({
        commission_percent: 0,
        min_commission_usd: 0,
        brand_name: '',
        primary_color: '',
        status: 'active' as 'active' | 'suspended' | 'cancelled',
        watermark_enabled: true
    })

    const adminFetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
        const headers = new Headers(init.headers || {})
        if (authToken) headers.set('Authorization', `Bearer ${authToken}`)
        return fetch(input, { ...init, headers })
    }

    // 테넌트 목록 불러오기
    const fetchTenants = async () => {
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
                    commission_percent: 10,
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
        }
    }, [isSuperAdmin])

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

    return (
        <div className="space-y-6">
            {/* 헤더 */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-black text-white">
                        {isKor ? '🏢 테넌트 관리' : '🏢 Tenant Management'}
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">
                        {isKor ? '수수료 및 브랜딩 설정' : 'Commission and branding settings'}
                    </p>
                </div>
                <button
                    onClick={() => setShowCreate(true)}
                    className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all"
                >
                    {isKor ? '+ 새 테넌트' : '+ New Tenant'}
                </button>
            </div>

            {/* 통계 카드 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">총 테넌트</div>
                    <div className="text-2xl font-black text-white mt-1">{tenants.length}</div>
                </div>
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">활성 테넌트</div>
                    <div className="text-2xl font-black text-green-400 mt-1">
                        {tenants.filter(t => t.status === 'active').length}
                    </div>
                </div>
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">평균 수수료율</div>
                    <div className="text-2xl font-black text-orange-400 mt-1">
                        {tenants.length > 0
                            ? (tenants.reduce((acc, t) => acc + t.commission_percent, 0) / tenants.length).toFixed(1)
                            : '0'}%
                    </div>
                </div>
                <div className="bg-[#0f172a]/60 border border-white/20 p-4 rounded-2xl">
                    <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">총 사용자</div>
                    <div className="text-2xl font-black text-blue-400 mt-1">
                        {tenants.reduce((acc, t) => acc + (t.user_count || 0), 0)}
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
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">브랜드 이름</th>
                                <th className="text-right px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">수수료율</th>
                                <th className="text-right px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">최소 수수료</th>
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">라이선스</th>
                                <th className="text-left px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">상태</th>
                                <th className="text-center px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">사용자</th>
                                <th className="text-center px-4 py-3 text-[10px] text-gray-500 font-black uppercase tracking-widest">작업</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={9} className="text-center py-8 text-gray-500">
                                        {isKor ? '로딩 중...' : 'Loading...'}
                                    </td>
                                </tr>
                            ) : tenants.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="text-center py-8 text-gray-500">
                                        {isKor ? '테넌트가 없습니다.' : 'No tenants found.'}
                                    </td>
                                </tr>
                            ) : (
                                tenants.map(tenant => (
                                    <tr key={tenant.tenant_key} className="border-b border-white/5 hover:bg-white/5">
                                        <td className="px-4 py-3">
                                            <div className="font-black text-white">{tenant.tenant_key}</div>
                                            {tenant.tenant_key === 'default' && (
                                                <span className="text-[9px] text-blue-400">기본</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-white">{tenant.brand_name || tenant.tenant_name}</td>
                                        <td className="px-4 py-3 text-right">
                                            <span className={`font-black ${tenant.commission_percent > 15 ? 'text-orange-400' : tenant.commission_percent > 10 ? 'text-yellow-400' : 'text-green-400'}`}>
                                                {tenant.commission_percent}%
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-right text-white">
                                            ${tenant.min_commission_usd}
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
                                        <td className="px-4 py-3 text-center text-white">
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
                                ))
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

            {/* 새 테넌트 생성 모달 */}
            {showCreate && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowCreate(false)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
                        <h2 className="text-lg font-black text-white mb-4">
                            {isKor ? '🏢 새 테넌트 생성' : '🏢 Create New Tenant'}
                        </h2>
                        <div className="space-y-3">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '테넌트 키' : 'Tenant Key'}
                                </label>
                                <input
                                    type="text"
                                    value={createForm.tenant_key}
                                    onChange={e => setCreateForm({ ...createForm, tenant_key: e.target.value })}
                                    placeholder="tenant_a"
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '테넌트 이름' : 'Tenant Name'}
                                </label>
                                <input
                                    type="text"
                                    value={createForm.tenant_name}
                                    onChange={e => setCreateForm({ ...createForm, tenant_name: e.target.value })}
                                    placeholder={isKor ? 'ABC Company' : 'ABC Company'}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '브랜드 이름' : 'Brand Name'}
                                </label>
                                <input
                                    type="text"
                                    value={createForm.brand_name}
                                    onChange={e => setCreateForm({ ...createForm, brand_name: e.target.value })}
                                    placeholder={isKor ? 'ABC Studio' : 'ABC Studio'}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '수수료율 (%)' : 'Commission (%)'}
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    max="100"
                                    step="0.5"
                                    value={createForm.commission_percent}
                                    onChange={e => setCreateForm({ ...createForm, commission_percent: Number(e.target.value) })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '최소 수수료 (USD)' : 'Min Commission (USD)'}
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={createForm.min_commission_usd}
                                    onChange={e => setCreateForm({ ...createForm, min_commission_usd: Number(e.target.value) })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '라이선스 티어' : 'License Tier'}
                                </label>
                                <select
                                    value={createForm.license_tier}
                                    onChange={e => setCreateForm({ ...createForm, license_tier: e.target.value as any })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="starter">Starter</option>
                                    <option value="standard">Standard</option>
                                    <option value="business">Business</option>
                                    <option value="enterprise">Enterprise</option>
                                </select>
                            </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button
                                onClick={handleCreateTenant}
                                className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all"
                            >
                                {isKor ? '생성' : 'Create'}
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
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowEdit(false)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
                        <h2 className="text-lg font-black text-white mb-4">
                            {isKor ? '⚙️ 테넌트 설정' : '⚙️ Tenant Settings'}
                        </h2>
                        <div className="space-y-3">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '브랜드 이름' : 'Brand Name'}
                                </label>
                                <input
                                    type="text"
                                    value={editForm.brand_name}
                                    onChange={e => setEditForm({ ...editForm, brand_name: e.target.value })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '수수료율 (%)' : 'Commission (%)'}
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    max="100"
                                    step="0.5"
                                    value={editForm.commission_percent}
                                    onChange={e => setEditForm({ ...editForm, commission_percent: Number(e.target.value) })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '최소 수수료 (USD)' : 'Min Commission (USD)'}
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={editForm.min_commission_usd}
                                    onChange={e => setEditForm({ ...editForm, min_commission_usd: Number(e.target.value) })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">
                                    {isKor ? '상태' : 'Status'}
                                </label>
                                <select
                                    value={editForm.status}
                                    onChange={e => setEditForm({ ...editForm, status: e.target.value as any })}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="active">Active</option>
                                    <option value="suspended">Suspended</option>
                                    <option value="cancelled">Cancelled</option>
                                </select>
                            </div>
                            <div className="flex items-center gap-3">
                                <input
                                    type="checkbox"
                                    id="watermark-enabled"
                                    checked={editForm.watermark_enabled}
                                    onChange={e => setEditForm({ ...editForm, watermark_enabled: e.target.checked })}
                                    className="w-4 h-4 accent-blue-500 cursor-pointer"
                                />
                                <label htmlFor="watermark-enabled" className="text-sm text-white">
                                    {isKor ? '워터마크 사용' : 'Enable Watermark'}
                                </label>
                            </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button
                                onClick={() => handleUpdateTenant(selectedTenant)}
                                className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all"
                            >
                                {isKor ? '저장' : 'Save'}
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
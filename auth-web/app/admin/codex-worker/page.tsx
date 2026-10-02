 'use client'
import {useCallback} from 'react'
import ScriptOperationsPanel from '@/components/ScriptOperationsPanel'
import {authedFetch,useAuthToken} from '../referrals/_hooks'
export default function Page(){
 const {token,ready}=useAuthToken()
 const fetchAdmin=useCallback((url:RequestInfo | URL,init?:RequestInit)=>authedFetch(token,String(url),init),[token])
 if(!ready)return <p>로그인 확인 중…</p>
 if(!token)return <p>관리자 로그인이 필요합니다.</p>
 return <main className="mx-auto max-w-6xl p-6"><ScriptOperationsPanel adminFetch={fetchAdmin} mode="worker"/></main>
}

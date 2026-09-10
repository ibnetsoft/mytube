import { ExternalAccountClient, GoogleAuth } from 'google-auth-library'
import { getVercelOidcToken } from '@vercel/oidc'

export async function voiceStudioAuth(project: string) {
    // Local development keeps ADC; production never silently falls back to it.
    if (!process.env.VERCEL) {
        return new GoogleAuth({projectId: project, scopes:['https://www.googleapis.com/auth/cloud-platform']}).getClient()
    }
    const number=process.env.GCP_PROJECT_NUMBER
    const pool=process.env.GCP_WORKLOAD_IDENTITY_POOL_ID
    const provider=process.env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID
    const account=process.env.GCP_SERVICE_ACCOUNT_EMAIL
    if (!number || !pool || !provider || !account) throw new Error('Voice Studio 운영 인증 설정이 누락됐습니다.')
    const client=ExternalAccountClient.fromJSON({
        type:'external_account',
        audience:`//iam.googleapis.com/projects/${number}/locations/global/workloadIdentityPools/${pool}/providers/${provider}`,
        subject_token_type:'urn:ietf:params:oauth:token-type:jwt',
        token_url:'https://sts.googleapis.com/v1/token',
        service_account_impersonation_url:`https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${account}:generateAccessToken`,
        scopes:['https://www.googleapis.com/auth/cloud-platform'],
        subject_token_supplier:{getSubjectToken:async()=>getVercelOidcToken()},
    })
    if(!client) throw new Error('Voice Studio 운영 인증을 초기화하지 못했습니다.')
    return client
}

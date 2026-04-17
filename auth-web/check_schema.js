const { createClient } = require('@supabase/supabase-js')

const supabase = createClient(
    'https://giorysjpgxzdypbmxwmx.supabase.co',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdpb3J5c2pwZ3h6ZHlwYm14d214Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTg0MTc3OSwiZXhwIjoyMDg1NDE3Nzc5fQ.bVpsP4y3NS1yXFpe0YZjKWCz_zHYOiXsEmm_GL3mXHw'
)

async function createMissingProfile() {
    const userId = 'ba2f2a43-c6ea-4fe2-a6a3-0f861d93afc6' // ejsh0519@naver.com

    const { data, error } = await supabase
        .from('profiles')
        .insert({
            id: userId,
            token_balance: 50000,
            membership_tier: 'pro'
        })
    
    if (error) {
        console.error('Error creating profile:', error.message)
    } else {
        console.log('Profile created successfully for', userId)
    }
}

createMissingProfile()

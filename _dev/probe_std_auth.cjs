const path = require('node:path');
const crypto = require('node:crypto');
require('../auth-web/node_modules/dotenv').config({ path: path.resolve('.env'), quiet: true });
const local = require('../auth-web/node_modules/dotenv').parse(require('node:fs').readFileSync('auth-web/.env.local'));
for (const [key,value] of Object.entries(local)) if (!process.env[key]) process.env[key] = value;
const email = 'supapitmusic@gmail.com';
const payload = `${email}.${Math.floor(Date.now()/1000)}`;
const secret = process.env.DESKTOP_SESSION_SECRET || process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!secret) throw Error('Missing session configuration');
const token = Buffer.from(`${payload}.${crypto.createHmac('sha256', secret).update(payload).digest('hex')}`).toString('base64url');
(async () => {
    for (const route of (process.argv.includes('--db') ? ['/rest/v1/profiles?select=id&email=eq.supapitmusic%40gmail.com&limit=1', '/auth/v1/health'] : ['/api/std/me', '/api/std/projects'])) {
        const start = Date.now();
        try {
            const db = process.argv.includes('--db');
            const headers = db ? { apikey: process.env.SUPABASE_SERVICE_ROLE_KEY, Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}` } : { Authorization: `Bearer ${token}` };
            const config = Object.entries(headers).map(([k,v]) => `header = "${k}: ${v}"`).join('\n');
            const raw = require('node:child_process').execFileSync('curl.exe',['-sS','--max-time','20','--config','-','-w','\n%{http_code}',(db ? process.env.NEXT_PUBLIC_SUPABASE_URL : 'https://studio.airing.work')+route], { input:config, encoding:'utf8' });
            const split = raw.lastIndexOf('\n');
            const body = raw.slice(0,split), res = { status:Number(raw.slice(split+1)) };
            let data; try { data=JSON.parse(body); } catch {}
            console.log(JSON.stringify({ route, status:res.status, ms:Date.now()-start, user:!!data?.user, success:data?.success, error:data?.error, nonJson: !data ? body.slice(0,180):undefined }));
        } catch(e) { console.log(JSON.stringify({route,ms:Date.now()-start,error:e.message})); }
    }
})().catch(e=>{console.error(e.message);process.exitCode=1});

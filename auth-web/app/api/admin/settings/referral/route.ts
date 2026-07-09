import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import { isAuthResponse, requireAdmin } from '../../_auth';

const getAdmin = () => createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
  { auth: { persistSession: false } }
);

const SETTING_KEYS = [
  'referral_mode',
  'referral_default_sponsor_uuid',
  'referral_level1_percent',
  'referral_level2_percent',
  'referral_min_payout',
  'referral_cycle'
];

export async function GET(req: Request) {
  try {
    const requester = await requireAdmin(req);
    if (isAuthResponse(requester)) return requester;

    const supabase = getAdmin();

    const { data, error } = await supabase
      .from('global_settings')
      .select('key, value')
      .in('key', SETTING_KEYS);

    if (error) throw error;

    const settings = SETTING_KEYS.reduce((acc, key) => {
      const row = data?.find((r) => r.key === key);
      acc[key] = row ? row.value : '';
      return acc;
    }, {} as Record<string, string>);

    return NextResponse.json({ settings });
  } catch (error: any) {
    console.error('[Admin] Failed to fetch referral settings:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const requester = await requireAdmin(request);
    if (isAuthResponse(requester)) return requester;

    const supabase = getAdmin();

    const payload = await request.json();

    // Validate referral_mode
    const validModes = ['OFF', 'NORMAL', 'PROMOTION'];
    if (payload.referral_mode && !validModes.includes(payload.referral_mode)) {
      return NextResponse.json({ error: 'Invalid referral_mode' }, { status: 400 });
    }

    // Validate referral_cycle
    const validCycles = ['REALTIME', 'DAILY', 'WEEKLY', 'MONTHLY', 'MANUAL'];
    if (payload.referral_cycle && !validCycles.includes(payload.referral_cycle)) {
      return NextResponse.json({ error: 'Invalid settlement_cycle' }, { status: 400 });
    }

    const updates = SETTING_KEYS.map((key) => {
      return {
        key,
        value: payload[key] ?? '',
        updated_at: new Date().toISOString()
      };
    });

    const { error } = await supabase
      .from('global_settings')
      .upsert(updates, { onConflict: 'key' });

    if (error) throw error;

    return NextResponse.json({ success: true });
  } catch (error: any) {
    console.error('[Admin] Failed to update referral settings:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

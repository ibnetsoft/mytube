import { SupabaseClient } from '@supabase/supabase-js';

export async function processSettlement(
  supabaseAdmin: SupabaseClient,
  sourceUserId: string,
  amount: number,
  sourceTxId: string
) {
  try {
    // 1. Fetch referral settings
    const { data: settingsData, error: settingsError } = await supabaseAdmin
      .from('global_settings')
      .select('key, value');

    if (settingsError) {
      console.error('[Settlement] Failed to fetch settings', settingsError);
      return;
    }

    const settings = settingsData?.reduce((acc: any, row: any) => {
      acc[row.key] = row.value;
      return acc;
    }, {}) || {};

    const mode = settings['referral_mode'] || 'OFF';
    if (mode === 'OFF') {
      console.log('[Settlement] Referral mode is OFF. Skipping settlement.');
      return;
    }

    const level1Percent = parseFloat(settings['referral_level1_percent'] || '10');
    const level2Percent = parseFloat(settings['referral_level2_percent'] || '5');

    // 2. Prevent duplicate processing (Code level)
    const { data: existingCommissions, error: existError } = await supabaseAdmin
      .from('referral_commissions')
      .select('id')
      .eq('metadata->>source_tx_id', sourceTxId);

    if (existError) {
      console.error('[Settlement] Failed to check existing commissions', existError);
      return;
    }

    if (existingCommissions && existingCommissions.length > 0) {
      console.log(`[Settlement] Commissions for tx ${sourceTxId} already exist. Skipping.`);
      return;
    }

    // 3. Fetch Level 1 Sponsor
    const { data: sourceProfile, error: profileError } = await supabaseAdmin
      .from('profiles')
      .select('referred_by')
      .eq('id', sourceUserId)
      .maybeSingle();

    if (profileError || !sourceProfile) {
      console.error('[Settlement] Failed to fetch source profile', profileError);
      return;
    }

    const level1SponsorId = sourceProfile.referred_by;
    if (!level1SponsorId) {
      console.log(`[Settlement] User ${sourceUserId} has no sponsor. Skipping.`);
      return;
    }

    if (level1SponsorId === sourceUserId) {
      console.warn(`[Settlement] Loop detected: L1 sponsor is self (${sourceUserId}). Skipping.`);
      return;
    }

    // 4. Calculate Level 1 Commission
    const level1Amount = Math.round(amount * (level1Percent / 100) * 100) / 100;
    
    const inserts = [];

    if (level1Amount > 0) {
      inserts.push({
        beneficiary_id: level1SponsorId,
        source_user_id: sourceUserId,
        commission_type: 'direct',
        base_tokens: amount,
        rate_percent: level1Percent,
        commission_tokens: level1Amount,
        status: 'pending',
        metadata: { source_tx_id: sourceTxId }
      });
    }

    // 5. Fetch Level 2 Sponsor
    const { data: l1Profile, error: l1ProfileError } = await supabaseAdmin
      .from('profiles')
      .select('referred_by')
      .eq('id', level1SponsorId)
      .maybeSingle();

    if (!l1ProfileError && l1Profile && l1Profile.referred_by) {
      const level2SponsorId = l1Profile.referred_by;
      
      // Loop or same sponsor prevention
      if (level2SponsorId !== sourceUserId && level2SponsorId !== level1SponsorId) {
        const level2Amount = Math.round(amount * (level2Percent / 100) * 100) / 100;
        
        if (level2Amount > 0) {
          inserts.push({
            beneficiary_id: level2SponsorId,
            source_user_id: sourceUserId,
            commission_type: 'level2',
            base_tokens: amount,
            rate_percent: level2Percent,
            commission_tokens: level2Amount,
            status: 'pending',
            metadata: { source_tx_id: sourceTxId }
          });
        }
      } else {
        console.warn(`[Settlement] Loop or duplicate L2 detected for ${sourceUserId} -> ${level1SponsorId} -> ${level2SponsorId}. Skipping L2.`);
      }
    }

    if (inserts.length > 0) {
      const { error: insertError } = await supabaseAdmin
        .from('referral_commissions')
        .insert(inserts);

      if (insertError) {
        console.error('[Settlement] Failed to insert commissions', insertError);
      } else {
        console.log(`[Settlement] Successfully inserted ${inserts.length} pending commission(s) for tx ${sourceTxId}`);
      }
    }

  } catch (error) {
    console.error('[Settlement] Unexpected error:', error);
  }
}

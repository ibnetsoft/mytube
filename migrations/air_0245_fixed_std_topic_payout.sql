-- AIR-0245: STD topic payout is fixed at 2.5 USDT regardless of scene count.

ALTER TABLE public.topics_queue
    ALTER COLUMN estimated_payout TYPE numeric USING estimated_payout::numeric;

UPDATE public.topics_queue
SET
    estimated_payout = 2.5,
    payout_policy = jsonb_build_object(
        'basis', 'fixed',
        'payout_usdt', 2.5,
        'scene_count_independent', true
    )
WHERE status IN ('pending', 'assigned');

UPDATE public.global_settings
SET value = '2.5'
WHERE key = 'sys_api_longform_base_payout';

UPDATE public.global_settings
SET value = '[{"max_minutes":150,"payout_usdt":2.5}]'
WHERE key = 'sys_api_longform_payout_tiers';

import asyncio
import traceback
import datetime
from config import config
from services.web_admin_client import web_admin_client

class ReferralEngagementService:
    def __init__(self):
        self.running = False
        self.interval_seconds = 3600 * 24 # Every 24 hours

    async def start_background_worker(self):
        if self.running:
            return
        self.running = True
        print("[ReferralEngagement] Background worker started")
        
        # Initial wait so it doesn't run immediately on startup
        await asyncio.sleep(60)

        while self.running:
            try:
                await asyncio.to_thread(self._process_reengagement)
            except Exception as e:
                print(f"[ReferralEngagement] Error: {e}")
                traceback.print_exc()
            
            await asyncio.sleep(self.interval_seconds)

    def _process_reengagement(self):
        """Finds inactive users with an active downline and triggers re-engagement notifications"""
        print("[ReferralEngagement] Processing re-engagement...")
        
        if not web_admin_client.supabase_url:
            print("[ReferralEngagement] Supabase URL missing")
            return

        try:
            # Trigger Re-engagement Notifications
            try:
                web_admin_client.rpc('trigger_reengagement_notifications', {})
            except Exception as e:
                print(f"[ReferralEngagement] Error triggering re-engagement notifications: {e}")
            
            # Trigger Habit Loop Reminders
            try:
                web_admin_client.rpc('trigger_habit_reminders', {})
            except Exception as e:
                print(f"[ReferralEngagement] Error triggering habit loop reminders: {e}")

        except Exception as e:
             print(f"[ReferralEngagement] process error: {e}")

referral_engagement_service = ReferralEngagementService()

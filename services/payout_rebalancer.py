"""
다이내믹 보상 리밸런싱 백그라운드 서비스
자동으로 수요 분석을 실행하고 보상 배수를 조정합니다.
"""
import os
import requests
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class PayoutRebalancerService:
    def __init__(self):
        self.running = False

    def _supabase_headers(self):
        supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not supabase_key:
            return None, None
        return supabase_url.rstrip("/"), {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }

    def get_settings(self) -> Dict[str, Any]:
        supabase_url, headers = self._supabase_headers()
        if not supabase_url:
            return {}

        try:
            res = requests.get(
                f"{supabase_url}/rest/v1/payout_rebalancing_settings",
                headers=headers,
                timeout=5,
                verify=False,
                proxies={"http": None, "https": None}
            )
            if res.status_code == 200:
                data = res.json()
                return data[0] if data else {}
        except Exception as e:
            logger.warning(f"[PayoutRebalancer] Failed to get settings: {e}")

        return {}

    def should_rebalance(self) -> bool:
        settings = self.get_settings()
        if not settings.get("enabled", False):
            return False

        next_rebalance = settings.get("next_rebalance_at")
        if not next_rebalance:
            return True

        try:
            return datetime.now() > datetime.fromisoformat(next_rebalance)
        except Exception:
            return True

    def run_rebalance(self):
        if not self.should_rebalance():
            logger.info("[PayoutRebalancer] Rebalance not scheduled yet")
            return

        logger.info(f"[PayoutRebalancer] Starting auto-rebalance at {datetime.now()}")

        supabase_url, headers = self._supabase_headers()
        settings = self.get_settings()

        # Get recent analytics
        days = 7
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        try:
            res = requests.get(
                f"{supabase_url}/rest/v1/payout_demand_analytics",
                params={
                    "period_start": f"gte.{start_date}",
                    "order": "period_start.desc"
                },
                headers=headers,
                timeout=10,
                verify=False,
                proxies={"http": None, "https": None}
            )

            if res.status_code != 200:
                logger.error(f"[PayoutRebalancer] Failed to get analytics: {res.text}")
                return

            analytics = res.json()
            adjustments_made = 0

            for item in analytics:
                category_id = item.get("category_id")
                current_mult = float(item.get("current_multiplier", 1.0))
                recommended_mult = float(item.get("recommended_multiplier", 1.0))

                # Only adjust if difference is significant
                if abs(current_mult - recommended_mult) < 0.1:
                    continue

                # Check if auto-apply is enabled
                if not settings.get("auto_apply_adjustments", False):
                    logger.info(
                        f"[PayoutRebalancer] Would adjust category {category_id}: "
                        f"{current_mult}x → {recommended_mult}x (auto-apply disabled)"
                    )
                    continue

                # Apply adjustment
                try:
                    requests.post(
                        f"{supabase_url}/rest/v1/category_priority_boosts",
                        json={
                            "category_id": category_id,
                            "boost_multiplier": recommended_mult,
                            "reason": "Auto-rebalancing based on demand analysis"
                        },
                        headers=headers,
                        timeout=5,
                        verify=False,
                        proxies={"http": None, "https": None}
                    )

                    # Log adjustment
                    requests.post(
                        f"{supabase_url}/rest/v1/payout_adjustment_history",
                        json={
                            "category_id": category_id,
                            "category_name": item.get("category_name"),
                            "language": item.get("language"),
                            "adjustment_type": "auto_rebalance",
                            "old_multiplier": current_mult,
                            "new_multiplier": recommended_mult,
                            "adjustment_percent": ((recommended_mult - current_mult) / current_mult * 100),
                            "reason": "Auto-rebalancing based on demand analysis",
                            "adjusted_by": "system",
                            "adjustment_source": "system",
                            "trigger_type": "scheduled"
                        },
                        headers=headers,
                        timeout=5,
                        verify=False,
                        proxies={"http": None, "https": None}
                    )

                    adjustments_made += 1
                    logger.info(
                        f"[PayoutRebalancer] Adjusted category {category_id}: "
                        f"{current_mult}x → {recommended_mult}x"
                    )
                except Exception as e:
                    logger.error(f"[PayoutRebalancer] Failed to adjust category {category_id}: {e}")

            # Update next rebalance time
            interval_hours = settings.get("rebalance_interval_hours", 6)
            next_rebalance = datetime.now() + timedelta(hours=interval_hours)

            try:
                requests.patch(
                    f"{supabase_url}/rest/v1/payout_rebalancing_settings",
                    json={
                        "last_rebalance_at": datetime.now().isoformat(),
                        "next_rebalance_at": next_rebalance.isoformat()
                    },
                    headers=headers,
                    timeout=5,
                    verify=False,
                    proxies={"http": None, "https": None}
                )
            except Exception as e:
                logger.error(f"[PayoutRebalancer] Failed to update next rebalance time: {e}")

            logger.info(
                f"[PayoutRebalancer] Completed. Made {adjustments_made} adjustments. "
                f"Next rebalance at {next_rebalance}"
            )

        except Exception as e:
            logger.error(f"[PayoutRebalancer] Rebalance failed: {e}")

    def start(self):
        if self.running:
            return

        self.running = True
        settings = self.get_settings()
        interval_hours = settings.get("rebalance_interval_hours", 6)
        interval_seconds = interval_hours * 3600

        logger.info(f"[PayoutRebalancer] Started. Running every {interval_hours} hours.")

        # Start in background thread
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()

    def _run_loop(self):
        while self.running:
            try:
                if self.should_rebalance():
                    self.run_rebalance()
            except Exception as e:
                logger.error(f"[PayoutRebalancer] Rebalance cycle error: {e}")

            # Wait for next interval
            settings = self.get_settings()
            interval_hours = settings.get("rebalance_interval_hours", 6)
            interval_seconds = interval_hours * 3600

            logger.info(f"[PayoutRebalancer] Sleeping for {interval_seconds} seconds...")
            for _ in range(interval_seconds):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("[PayoutRebalancer] Stopped")

    def stop(self):
        self.running = False


# Global instance
payout_rebalancer = PayoutRebalancerService()


def start_rebalancer_if_enabled():
    """설정이 활성화되어 있으면 리밸런서를 시작합니다."""
    settings = payout_rebalancer.get_settings()
    if settings.get("enabled", False):
        logger.info("[PayoutRebalancer] Auto-rebalancing enabled, starting service...")
        payout_rebalancer.start()
    else:
        logger.info("[PayoutRebalancer] Auto-rebalancing disabled, service not started")
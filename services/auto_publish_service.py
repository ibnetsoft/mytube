import os
import threading
import time
from datetime import datetime

import requests

import database as db
from services.project_publish_service import publish_project_to_youtube, release_project_to_public
from services.web_admin_client import web_admin_client


class AutoPublishService:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 15
        self.auth_server_url = web_admin_client.dashboard_url

    def get_remote_user_id(self):
        license_value = ""
        if os.path.exists("license.key"):
            with open("license.key", "r", encoding="utf-8") as f:
                license_value = f.read().strip()
        try:
            from services.auth_service import auth_service
            email = auth_service.get_user_email()
        except Exception:
            email = ""
        if not email:
            email = db.get_global_setting("user_email", "") or ""
        return web_admin_client.resolve_user_id(email=email, candidate=license_value)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[Auto Publish] Service started.")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self._check_and_publish()
            except Exception as e:
                print(f"[Error] AutoPublish error: {e}")
            time.sleep(self.interval)

    def _check_and_publish(self):
        from services.auth_service import auth_service

        if auth_service.is_restricted():
            return

        user_id = self.get_remote_user_id()
        if not user_id:
            return

        try:
            res = requests.get(f"{self.auth_server_url}/api/publishing?userId={user_id}", timeout=10)
            if res.status_code != 200:
                return

            data = res.json()
            requests_list = data.get("requests", [])
            publish_queue = [r for r in requests_list if r.get("status") in ("approved", "to_be_published")]
            release_queue = [r for r in requests_list if r.get("status") == "release_requested"]

            if release_queue:
                self._process_release_queue(release_queue)

            if not publish_queue:
                return

            print(f"[Info] Found {len(publish_queue)} videos to be published to YouTube.")

            for index, req in enumerate(publish_queue):
                req_id = req.get("id")
                metadata = req.get("metadata") or {}
                project_id = metadata.get("project_id")

                if not project_id:
                    print(f"[Warning] Request {req_id} missing project_id in metadata.")
                    continue

                try:
                    db.update_project_setting(int(project_id), "admin_publish_status", str(req.get("status") or "approved"))
                    # [private-first release flow] Videos upload as private by
                    # default so a human can watch the actual rendered output
                    # before it goes live - this must not silently fall back to
                    # "public" if metadata.privacy_status is ever missing.
                    result = publish_project_to_youtube(
                        int(project_id),
                        requested_privacy=str(metadata.get("privacy_status") or "private"),
                        requested_publish_at=metadata.get("publish_at"),
                        requested_channel_id=metadata.get("channel_id"),
                    )

                    merged_metadata = {
                        **metadata,
                        "videoId": result.get("video_id"),
                        "youtube_url": result.get("url"),
                        "upload_source": result.get("upload_source"),
                        "published_at": datetime.utcnow().isoformat() + "Z",
                    }

                    patch_res = web_admin_client.supabase_patch(
                        "publishing_requests",
                        {
                            "status": "published",
                            "video_url": result.get("url"),
                            "metadata": merged_metadata,
                        },
                        params={"id": f"eq.{req_id}"},
                        timeout=15,
                    )

                    if patch_res is not None and patch_res.status_code in (200, 204):
                        print(f"[Success] Published request {req_id}: {result.get('url')}")
                    else:
                        body = patch_res.text[:200] if patch_res is not None else "no response"
                        print(f"[Warning] Server update failed for request {req_id}: {body}")

                    if index < len(publish_queue) - 1:
                        print("[Auto Publish] Waiting 15 seconds before the next publish job.")
                        time.sleep(15)

                except Exception as e:
                    err_msg = str(e)
                    print(f"[Error] Failed to publish request {req_id}: {err_msg}")
                    try:
                        db.update_project_setting(int(project_id), "admin_publish_status", "publish_failed")
                        db.update_project_setting(int(project_id), "admin_publish_error", err_msg)
                    except Exception:
                        pass
                    try:
                        web_admin_client.supabase_patch(
                            "publishing_requests",
                            {
                                "status": "failed",
                                "metadata": {
                                    **metadata,
                                    "publish_error": err_msg,
                                    "failed_at": datetime.utcnow().isoformat() + "Z",
                                },
                            },
                            params={"id": f"eq.{req_id}"},
                            timeout=5,
                        )
                    except Exception:
                        pass

        except Exception:
            pass

    def _process_release_queue(self, release_queue):
        print(f"[Info] Found {len(release_queue)} videos to release to public.")
        for req in release_queue:
            req_id = req.get("id")
            metadata = req.get("metadata") or {}
            project_id = metadata.get("project_id")

            if not project_id:
                print(f"[Warning] Release request {req_id} missing project_id in metadata.")
                continue

            try:
                result = release_project_to_public(int(project_id), requested_channel_id=metadata.get("channel_id"))

                patch_res = web_admin_client.supabase_patch(
                    "publishing_requests",
                    {
                        "status": "public",
                        "metadata": {
                            **metadata,
                            "made_public_at": datetime.utcnow().isoformat() + "Z",
                        },
                    },
                    params={"id": f"eq.{req_id}"},
                    timeout=15,
                )

                if patch_res is not None and patch_res.status_code in (200, 204):
                    print(f"[Success] Released to public {req_id}: {result.get('url')}")
                else:
                    body = patch_res.text[:200] if patch_res is not None else "no response"
                    print(f"[Warning] Server update failed for release {req_id}: {body}")

            except Exception as e:
                err_msg = str(e)
                print(f"[Error] Failed to release {req_id} to public: {err_msg}")
                try:
                    web_admin_client.supabase_patch(
                        "publishing_requests",
                        {
                            "status": "published",
                            "metadata": {
                                **metadata,
                                "release_error": err_msg,
                                "release_failed_at": datetime.utcnow().isoformat() + "Z",
                            },
                        },
                        params={"id": f"eq.{req_id}"},
                        timeout=5,
                    )
                except Exception:
                    pass


auto_publish_service = AutoPublishService()

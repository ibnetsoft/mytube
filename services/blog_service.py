import os
import json
import httpx
from typing import Optional, Dict, Any, List
from services.source_service import source_service
from services.gemini_service import gemini_service
import database as db
from config import config

class BlogService:
    def __init__(self):
        pass

    async def generate_blog_from_source(
        self, 
        source_type: str, 
        source_value: str, 
        platform: str, 
        blog_style: str, 
        language: str = "ko",
        user_notes: str = ""
    ) -> Dict[str, Any]:
        """소스로부터 블로그 포스팅 생성 핵심 로직"""
        try:
            # 1. 소스 내용 추출
            content_data = {}
            if source_type == "youtube":
                content_data = await source_service.extract_text_from_youtube(source_value)
            elif source_type == "url":
                content_data = await source_service.extract_text_from_url(source_value)
            elif source_type == "text":
                content_data = {"title": "사용자 입력 텍스트", "content": source_value}
            else:
                return {"status": "error", "error": f"지원하지 않는 소스 유형입니다: {source_type}"}

            if not content_data.get("content"):
                return {"status": "error", "error": "소스에서 내용을 추출하지 못했습니다."}

            # 2. 블로그 생성 (Gemini)
            blog_data = await gemini_service.generate_blog_content(
                source_content=content_data["content"],
                platform=platform,
                blog_style=blog_style,
                language=language,
                user_notes=user_notes
            )

            if "error" in blog_data:
                return {"status": "error", "error": blog_data["error"]}

            return {
                "status": "ok",
                "title": blog_data.get("title"),
                "content": blog_data.get("content"),
                "tags": blog_data.get("tags", []),
                "summary": blog_data.get("summary"),
                "source_title": content_data.get("title")
            }

        except Exception as e:
            print(f"BlogService Error: {e}")
            return {"status": "error", "error": str(e)}

    async def post_to_wordpress(
        self, 
        title: str, 
        content: str, 
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """워드프레스에 글 게시"""
        try:
            import base64
            from config import config
            wp_url = config.WP_URL.rstrip('/')
            username = config.WP_USERNAME
            password = config.WP_PASSWORD

            if not wp_url or not username or not password:
                # DB에서 다시 로드 시도
                wp_url = db.get_global_setting("wp_url", "").rstrip('/')
                username = db.get_global_setting("wp_username", "")
                password = db.get_global_setting("wp_password", "")

            if not wp_url or not username or not password:
                return {"status": "error", "error": "워드프레스 설정(URL, 사용자명, 앱 비밀번호)이 되어있지 않습니다."}

            endpoint = f"{wp_url}/wp-json/wp/v2/posts"
            
            # Basic Auth Header
            auth_str = f"{username}:{password}"
            auth_bytes = auth_str.encode("utf-8")
            auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")
            headers = {
                "Authorization": f"Basic {auth_base64}",
                "Content-Type": "application/json"
            }

            payload = {
                "title": title,
                "content": content,
                "status": "publish"
            }
            
            # 태그 처리 (워드프레스는 태그 ID 배열을 받으므로, 일단 텍스트로 추가하는 방식이나 simple하게 처리)
            # 여기서는 기본적으로 제목과 내용만 게시합니다.

            async with httpx.AsyncClient(follow_redirects=True) as client:
                res = await client.post(endpoint, json=payload, headers=headers, timeout=30)

                if res.status_code in [200, 201]:
                    data = res.json()
                    post_id = data.get("id")
                    url = data.get("link")
                    return {
                        "status": "ok", 
                        "post_id": post_id, 
                        "url": url,
                        "message": "워드프레스에 성공적으로 게시되었습니다."
                    }
                else:
                    try:
                        error_data = res.json()
                        error_msg = error_data.get("message", res.text)
                    except:
                        error_msg = res.text
                    return {"status": "error", "error": f"워드프레스 게시 실패: {error_msg}"}

        except Exception as e:
            print(f"post_to_wordpress Error: {e}")
            return {"status": "error", "error": str(e)}

    async def upload_image_to_wordpress(self, image_path: str, filename: str = None) -> Dict[str, Any]:
        """이미지를 WordPress Media Library에 업로드하고 URL 반환"""
        try:
            import base64
            wp_url = config.WP_URL.rstrip('/') if config.WP_URL else ""
            username = config.WP_USERNAME or ""
            password = config.WP_PASSWORD or ""

            if not wp_url or not username or not password:
                wp_url = db.get_global_setting("wp_url", "").rstrip('/')
                username = db.get_global_setting("wp_username", "")
                password = db.get_global_setting("wp_password", "")

            if not wp_url or not username or not password:
                return {"status": "error", "error": "워드프레스 설정이 되어있지 않습니다."}

            endpoint = f"{wp_url}/wp-json/wp/v2/media"
            auth_str = f"{username}:{password}"
            auth_base64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

            if not filename:
                filename = os.path.basename(image_path)

            # MIME type 감지
            ext = os.path.splitext(filename)[1].lower()
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
            mime_type = mime_map.get(ext, 'image/png')

            with open(image_path, 'rb') as f:
                image_data = f.read()

            headers = {
                "Authorization": f"Basic {auth_base64}",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": mime_type
            }

            async with httpx.AsyncClient(follow_redirects=True) as client:
                res = await client.post(endpoint, content=image_data, headers=headers, timeout=60)
                if res.status_code in [200, 201]:
                    data = res.json()
                    return {
                        "status": "ok",
                        "media_id": data.get("id"),
                        "url": data.get("source_url", data.get("guid", {}).get("rendered", "")),
                    }
                else:
                    return {"status": "error", "error": f"WordPress 이미지 업로드 실패 ({res.status_code}): {res.text[:200]}"}

        except Exception as e:
            print(f"upload_image_to_wordpress Error: {e}")
            return {"status": "error", "error": str(e)}

    async def post_to_blogger(
        self,
        title: str,
        content: str,
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """구글 블로그(Blogger)에 글 게시 - API Key 방식"""
        try:
            # 설정 로드 (config → DB fallback)
            blog_id = config.BLOG_ID or db.get_global_setting("blog_id", "")
            api_key = config.GEMINI_API_KEY or db.get_global_setting("gemini", "")

            # Blogger API는 OAuth2가 정석이지만, API Key로도 게시 가능
            # 단, API Key만으로는 쓰기 권한이 없으므로 OAuth2 access token 필요
            # 여기서는 client_id/secret으로 저장된 refresh_token을 사용
            client_id = config.BLOG_CLIENT_ID or db.get_global_setting("blog_client_id", "")
            client_secret = config.BLOG_CLIENT_SECRET or db.get_global_setting("blog_client_secret", "")

            if not blog_id:
                return {"status": "error", "error": "블로그 ID가 설정되지 않았습니다. (설정 → API 설정)"}

            if not client_id or not client_secret:
                return {"status": "error", "error": "Google Blog API 클라이언트 ID/비밀번호가 설정되지 않았습니다."}

            # 1. Refresh Token으로 Access Token 획득
            access_token = await self._get_blogger_access_token(client_id, client_secret)
            if not access_token:
                return {"status": "error", "error": "Blogger 인증 실패. OAuth 토큰을 갱신해주세요. (설정 → Google Blog API → 연결확인)"}

            # 2. Blogger API v3로 포스트 게시
            endpoint = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # HTML 변환 (줄바꿈 → <br>)
            html_content = content.replace('\n', '<br>\n')

            payload = {
                "kind": "blogger#post",
                "blog": {"id": blog_id},
                "title": title,
                "content": html_content
            }

            if tags:
                payload["labels"] = tags

            async with httpx.AsyncClient() as client:
                res = await client.post(endpoint, json=payload, headers=headers, timeout=30)

                if res.status_code in [200, 201]:
                    data = res.json()
                    return {
                        "status": "ok",
                        "post_id": data.get("id"),
                        "url": data.get("url"),
                        "message": "구글 블로그에 성공적으로 게시되었습니다."
                    }
                else:
                    try:
                        error_data = res.json()
                        error_msg = error_data.get("error", {}).get("message", res.text)
                    except Exception:
                        error_msg = res.text
                    return {"status": "error", "error": f"Blogger 게시 실패 ({res.status_code}): {error_msg}"}

        except Exception as e:
            print(f"post_to_blogger Error: {e}")
            return {"status": "error", "error": str(e)}

    async def _get_blogger_access_token(self, client_id: str, client_secret: str) -> Optional[str]:
        """저장된 refresh_token으로 access_token 갱신"""
        try:
            # DB에 저장된 refresh_token 조회
            refresh_token = db.get_global_setting("blog_refresh_token", "")
            if not refresh_token:
                # token 파일에서 로드 시도
                token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blog_token.json")
                if os.path.exists(token_path):
                    with open(token_path, "r") as f:
                        token_data = json.load(f)
                        refresh_token = token_data.get("refresh_token", "")
                        if not refresh_token:
                            return None

            if not refresh_token:
                return None

            # Google OAuth2 token refresh
            async with httpx.AsyncClient() as client:
                res = await client.post("https://oauth2.googleapis.com/token", data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                })

                if res.status_code == 200:
                    data = res.json()
                    return data.get("access_token")
                else:
                    print(f"Token refresh failed: {res.status_code} {res.text}")
                    return None

        except Exception as e:
            print(f"_get_blogger_access_token Error: {e}")
            return None

blog_service = BlogService()

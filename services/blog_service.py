import os
import json
import httpx
from typing import Optional, Dict, Any, List
from services.source_service import source_service
from services.gemini_service import gemini_service
import database as db
from config import config

class BlogService:
    async def process_blog_automation_v2(
        self,
        project_id: int,
        platform: str = "wordpress",
        blog_style: str = "info",
        language: str = "ko",
        user_notes: str = ""
    ) -> Dict[str, Any]:
        """프로젝트 데이터를 기반으로 제목, 본문, 이미지를 자동으로 생성 및 구성"""
        try:
            # 1. 프로젝트 데이터(대본) 로드
            script_data = db.get_script(project_id)
            if not script_data or not script_data.get("full_script"):
                # 숏츠 대본이라도 있는지 확인
                shorts_data = db.get_shorts(project_id)
                if shorts_data and shorts_data.get("shorts_data"):
                    scenes = shorts_data.get("shorts_data", {}).get("scenes", [])
                    if not scenes and isinstance(shorts_data.get("shorts_data"), list):
                        scenes = shorts_data.get("shorts_data")
                    script = "\n".join([(s.get("narration") or s.get("dialogue") or "") for s in scenes])
                else:
                    return {"status": "error", "error": "대본이 없습니다. 먼저 대본을 생성해주세요."}
            else:
                script = script_data["full_script"]

            # 2. 블로그 본문 및 제목 생성 (Gemini)
            # user_notes에 이미지 삽입 위치 가이드 추가
            enhanced_notes = user_notes + "\n본문 중간(1/3 지점쯤)에 [IMAGE_HERE_1] 태그를 하나만 넣으세요. 이미지는 1장만 생성됩니다."
            
            blog_result = await self.generate_blog_from_source(
                source_type="text",
                source_value=script,
                platform=platform,
                blog_style=blog_style,
                language=language,
                user_notes=enhanced_notes
            )

            if blog_result["status"] != "ok":
                return blog_result

            title = blog_result["title"]
            content = blog_result["content"]
            tags = blog_result.get("tags", [])

            # 3. 이미지 생성 프롬프트 자동 추출
            # 본문 내용을 기반으로 상징적인 이미지 프롬프트 생성
            image_prompt_text = await self.generate_image_prompt_from_content(content)
            
            # 4. 이미지 생성 (Google Imagen)
            # 대표 이미지 1개만 생성 (같은 프롬프트로 여러 장 생성 시 중복 발생 방지)
            generated_images = []
            try:
                # Imagen API 호출 (gemini_service 내장 기능 활용)
                from services.gemini_service import gemini_service

                # 16:9 비율로 고품질 이미지 1장 생성
                image_bytes_list = await gemini_service.generate_image(
                    prompt=image_prompt_text,
                    aspect_ratio="16:9",
                    num_images=1
                )

                if image_bytes_list:
                    from main import get_project_output_dir
                    import time
                    abs_dir, web_dir = get_project_output_dir(project_id)
                    
                    for i, img_bytes in enumerate(image_bytes_list):
                        filename = f"blog_img_{project_id}_{int(time.time())}_{i}.png"
                        save_path = os.path.join(abs_dir, filename)
                        web_url = f"{web_dir}/{filename}"
                        
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        
                        generated_images.append(web_url)
                
            except Exception as img_err:
                print(f"Blog auto image generation failed: {img_err}")

            # 5. 본문에 이미지 태그 삽입
            # [IMAGE_HERE_1], [IMAGE_HERE_2] 태그를 실제 <img> 태그로 치환
            final_content = content
            for i, img_url in enumerate(generated_images):
                tag = f"[IMAGE_HERE_{i+1}]"
                img_html = f'<div style="text-align:center; margin:20px 0;"><img src="{img_url}" style="max-width:100%; border-radius:12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);"></div>'
                if tag in final_content:
                    final_content = final_content.replace(tag, img_html)
                else:
                    # 태그가 없으면 본문 중간쯤에 삽입
                    paragraphs = final_content.split('</p>')
                    mid = len(paragraphs) // 3  # 1/3 지점
                    if mid > 0 and len(paragraphs) > 2:
                        paragraphs.insert(mid, f'</p>\n{img_html}\n')
                        final_content = '</p>'.join(paragraphs)
                    else:
                        # 문단 분리가 안 되면 상단에 배치
                        final_content = img_html + "\n\n" + final_content

            # [IMAGE_HERE_X] 남은 태그 제거
            import re
            final_content = re.sub(r'\[IMAGE_HERE_\d+\]', '', final_content)

            return {
                "status": "ok",
                "title": title,
                "content": final_content,
                "tags": tags,
                "images": generated_images,
                "image_prompt": image_prompt_text
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

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

    async def upload_local_images_to_public(self, content: str) -> str:
        """본문 내 로컬 이미지(/output/)를 WordPress에 업로드하여 공개 URL로 일괄 치환.
        모든 플랫폼에서 재사용 가능한 공개 URL을 반환."""
        import re
        import urllib.parse

        img_pattern = re.compile(r'<img [^>]*src="(/output/[^"]+)"[^>]*>')
        matches = img_pattern.findall(content)

        if not matches:
            return content

        processed = content
        uploaded_cache = {}
        failed_paths = []

        for local_path in matches:
            if local_path in uploaded_cache:
                processed = processed.replace(local_path, uploaded_cache[local_path])
                continue

            decoded_path = urllib.parse.unquote(local_path)
            if decoded_path.startswith("/output/"):
                rel_path = decoded_path[8:]
                abs_path = os.path.join(config.OUTPUT_DIR, rel_path)

                if os.path.exists(abs_path):
                    print(f"[ImageUpload] Uploading: {abs_path}")
                    upload_res = await self.upload_image_to_wordpress(abs_path)
                    if upload_res["status"] == "ok":
                        public_url = upload_res["url"]
                        uploaded_cache[local_path] = public_url
                        processed = processed.replace(local_path, public_url)
                        print(f"[ImageUpload] OK → {public_url}")
                    else:
                        print(f"[ImageUpload] FAIL: {upload_res.get('error')}")
                        failed_paths.append(local_path)
                else:
                    print(f"[ImageUpload] File not found: {abs_path}")
                    failed_paths.append(local_path)
            else:
                failed_paths.append(local_path)

        # 업로드 실패한 이미지 태그 제거 (깨진 아이콘 방지)
        for fp in failed_paths:
            processed = re.sub(
                r'<div[^>]*>\s*<img[^>]*src="' + re.escape(fp) + r'"[^>]*>\s*</div>',
                '', processed
            )
            processed = re.sub(
                r'<img[^>]*src="' + re.escape(fp) + r'"[^>]*>',
                '', processed
            )

        return processed

    async def post_to_wordpress(
        self,
        title: str,
        content: str, 
        tags: List[str] = None,
        categories: List[int] = None
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

            if not wp_url:
                wp_url = ""
            
            endpoint = f"{wp_url.rstrip('/')}/index.php?rest_route=/wp/v2/posts"
            
            # Basic Auth Header
            auth_str = f"{username}:{password}"
            auth_bytes = auth_str.encode("utf-8")
            auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")
            headers = {
                "Authorization": f"Basic {auth_base64}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            # 이미지는 라우터(post_blog)에서 사전 업로드 완료됨 → content에 공개 URL 포함
            processed_content = content

            # <style> 블록이 포함된 HTML은 WordPress 블록 에디터의 Custom HTML 블록으로 감싸기
            # WordPress REST API가 <style> 태그를 strip하지 않도록 보호
            import re
            if re.search(r'<style[\s\S]*?</style>', processed_content, re.IGNORECASE):
                # Gutenberg Custom HTML 블록으로 래핑
                processed_content = f'<!-- wp:html -->\n{processed_content}\n<!-- /wp:html -->'

            payload = {
                "title": title,
                "content": processed_content,
                "status": "publish",
                "categories": categories or []
            }
            
            # 태그 처리 (워드프레스는 태그 ID 배열을 받음)
            tag_ids = []
            if tags:
                try:
                    # 간단하게 태그를 이름으로 게시하고 싶지만 WP REST API는 ID만 받으므로
                    # 태그 이름들을 content 하단에 해시태그로 추가하거나, 추후 태그 생성 로직 추가 가능
                    footer_tags = "\n\n" + " ".join([f"#{t}" for t in tags])
                    payload["content"] += footer_tags
                except:
                    pass

            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
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
                        err_code = error_data.get("code", "unknown")
                        err_msg = error_data.get("message", res.text)
                        
                        full_error = f"워드프레스 API 오류({res.status_code}): {err_msg} [{err_code}]"
                        if res.status_code == 401:
                            full_error += "\n(아이디가 'admin'이 맞는지, 앱 비밀번호에 공백이 포함되었는지 확인하세요.)"
                        elif res.status_code == 403:
                            full_error += "\n(보안 플러그인에 의해 차단되었을 수 있습니다. index.php 우회 방식을 적용했습니다.)"
                    except:
                        full_error = f"워드프레스 응답 오류({res.status_code}): {res.text[:200]}"
                    
                    return {"status": "error", "error": full_error}


        except Exception as e:
            print(f"post_to_wordpress Error: {e}")
            return {"status": "error", "error": str(e)}

    async def upload_image_to_wordpress(self, image_path: str, filename: str = None) -> Dict[str, Any]:
        """이미지를 WordPress Media Library에 업로드하고 URL 반환"""
        try:
            import base64
            wp_url = config.WP_URL
            username = config.WP_USERNAME
            password = config.WP_PASSWORD

            if not (wp_url and username and password):
                # DB에서 다시 로드 시도
                wp_url = db.get_global_setting("wp_url", "")
                username = db.get_global_setting("wp_username", "")
                password = db.get_global_setting("wp_password", "")

            if not (wp_url and username and password):
                return {"status": "error", "error": "워드프레스 설정(URL, 사용자명, 앱 비밀번호)이 되어있지 않습니다. 설정 페이지에서 '저장' 버튼을 눌러주세요."}
            
            wp_url = wp_url.rstrip('/')
            endpoint = f"{wp_url}/index.php?rest_route=/wp/v2/media"
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
                return {"status": "error", "error": "Blogger 인증 실패. 설정 페이지의 'Google 블로그 연동' (OAuth) 버튼을 눌러 인증을 완료해주세요. (Refresh Token이 없습니다.)"}


            # 2. Blogger API v3로 포스트 게시
            endpoint = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # 이미지는 라우터(post_blog)에서 사전 업로드 완료됨 → content에 공개 URL 포함
            # 텍스트만 있으면 <br> 변환
            import re
            if re.search(r'<[a-z][\s\S]*>', content, re.IGNORECASE):
                html_content = content
            else:
                html_content = content.replace('\n', '<br>\n')

            payload = {
                "kind": "blogger#post",
                "blog": {"id": blog_id},
                "title": title,
                "content": html_content
            }

            if tags:
                payload["labels"] = tags

            print(f"[Blogger] Posting: title='{title[:50]}', content_len={len(html_content)}, tags={tags}")
            async with httpx.AsyncClient() as client:
                res = await client.post(endpoint, json=payload, headers=headers, timeout=60)

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

    async def translate_blog(self, title: str, content: str, target_language: str) -> Dict[str, Any]:
        """블로그 제목과 본문을 다른 언어로 번역 (HTML 구조/CSS 완벽 보존, 텍스트만 번역)"""
        import re

        lang_names = {"ko": "Korean", "en": "English", "ja": "Japanese", "vi": "Vietnamese"}
        target_name = lang_names.get(target_language, target_language)

        # ── 1단계: 보존할 블록을 플레이스홀더로 치환 ──
        preserve_store = {}
        counter = [0]

        def make_placeholder(match):
            key = f"__PRESERVE_{counter[0]}__"
            preserve_store[key] = match.group(0)
            counter[0] += 1
            return key

        safe_content = content

        # <style>...</style> 블록 보존
        safe_content = re.sub(r'<style[\s\S]*?</style>', make_placeholder, safe_content, flags=re.IGNORECASE)

        # <head>...</head> 블록 보존 (있을 경우)
        safe_content = re.sub(r'<head[\s\S]*?</head>', make_placeholder, safe_content, flags=re.IGNORECASE)

        # <!DOCTYPE ...>, <html ...>, <body ...> 태그 보존
        safe_content = re.sub(r'<!DOCTYPE[^>]*>', make_placeholder, safe_content, flags=re.IGNORECASE)
        safe_content = re.sub(r'<html[^>]*>', make_placeholder, safe_content, flags=re.IGNORECASE)
        safe_content = re.sub(r'</html>', make_placeholder, safe_content, flags=re.IGNORECASE)
        safe_content = re.sub(r'<body[^>]*>', make_placeholder, safe_content, flags=re.IGNORECASE)
        safe_content = re.sub(r'</body>', make_placeholder, safe_content, flags=re.IGNORECASE)

        # <script>...</script> 블록 보존
        safe_content = re.sub(r'<script[\s\S]*?</script>', make_placeholder, safe_content, flags=re.IGNORECASE)

        # 이미지/미디어 블록 보존
        safe_content = re.sub(
            r'<div[^>]*class="separator"[^>]*>[\s\S]*?</div>|'
            r'<div[^>]*>\s*<img[^>]*>\s*</div>|'
            r'<figure[^>]*>.*?</figure>|'
            r'<img[^>]*>',
            make_placeholder, safe_content, flags=re.DOTALL
        )

        # 테이블은 보존하지 않음 - 테이블 내 텍스트도 번역 필요

        from services.gemini_service import GeminiService
        gemini = GeminiService()

        # ── 2단계: 제목 번역 (별도 호출) ──
        new_title = title
        if title and title.strip():
            title_prompt = f"Translate the following title into {target_name}. Output ONLY the translated title, nothing else.\n\n{title}"
            print(f"[Translate] Translating title to {target_name}: '{title[:50]}'")
            try:
                translated_title = await gemini.generate_text(title_prompt, temperature=0.1, max_tokens=256)
                translated_title = translated_title.strip().strip('"').strip("'")
                # Gemini가 붙이는 라벨/접두어 제거
                translated_title = re.sub(r'^\[.*?\]\s*', '', translated_title)
                translated_title = re.sub(r'^(Title|제목|タイトル|翻訳)\s*[:：]\s*', '', translated_title, flags=re.IGNORECASE)
                if translated_title and translated_title != title:
                    new_title = translated_title
                    print(f"[Translate] Title translated: '{new_title[:50]}'")
                else:
                    print(f"[Translate] WARNING: Title unchanged after translation")
            except Exception as te:
                print(f"[Translate] Title translation error: {te}")

        # ── 3단계: 본문 번역 ──
        content_prompt = f"""You are a professional translator. Translate ALL Korean text in the following HTML into {target_name}.

RULES:
1. Translate ALL human-readable Korean text into {target_name} (including text in <table>, <th>, <td>, headings, paragraphs, spans, etc.)
2. Keep ALL HTML tags, attributes, and structure EXACTLY as they are.
3. Keep ALL __PRESERVE_X__ placeholders EXACTLY as they are.
4. Keep emoji, numbers, proper nouns (person names, team names) as-is or transliterate them naturally.
5. Do NOT wrap output in markdown code blocks.
6. Output ONLY the translated HTML. No explanations, no labels.

HTML TO TRANSLATE:
{safe_content}"""

        print(f"[Translate] Translating content to {target_name}, content_len={len(safe_content)}")
        translated_content = await gemini.generate_text(content_prompt, temperature=0.3, max_tokens=32768)

        if not translated_content or len(translated_content.strip()) < 10:
            print(f"[Translate] ERROR: Empty or too short response from Gemini")
            return {"status": "error", "error": "번역 결과가 비어있습니다. Gemini API를 확인해주세요."}

        new_content = translated_content.strip()

        # Gemini가 markdown 코드 블록으로 감싸는 경우 제거
        new_content = re.sub(r'^```html?\s*\n?', '', new_content)
        new_content = re.sub(r'\n?```\s*$', '', new_content)

        print(f"[Translate] Content translated. first_100='{new_content[:100]}'")

        # ── 4단계: 플레이스홀더 → 원본 복원 ──
        for key, original in preserve_store.items():
            new_content = new_content.replace(key, original)

        # 번역 검증: 원본과 동일하면 실패
        if new_content == content and target_language != 'ko':
            print(f"[Translate] ERROR: Content unchanged - translation failed")
            return {"status": "error", "error": f"{target_name} 번역에 실패했습니다. 내용이 변경되지 않았습니다."}

        print(f"[Translate] Done. new_title='{new_title[:50]}', new_content_len={len(new_content)}")

        return {
            "status": "ok",
            "title": new_title,
            "content": new_content
        }

    async def generate_image_prompt_from_content(self, content: str) -> str:
        """블로그 본문을 요약하여 이미지 생성을 위한 고품질 영어 프롬프트 생성 (인포그래픽 스타일)"""
        from services.gemini_service import GeminiService
        gemini = GeminiService()
        
        prompt = f"""
        당신은 블로그 비주얼 디렉터이자 인포그래픽 디자이너입니다. 
        아래 블로그 본문의 핵심 내용을 파악하고, 이 글의 주제를 시각화할 수 있는 '이미지 생성형 AI용 고품질 영어 프롬프트'를 하나만 작성해주세요.
        
        [지침]
        1. 스타일: 반드시 'Professional Infographic style'로 작성하세요.
        2. 구성: 만약 스포츠 경기나 국가 대항전 내용이라면, 양 팀의 'Team Emblems' 또는 'National Flags'가 세련되고 고급스럽게(premium layout) 배치되도록 묘사하세요.
        3. 시각 요소: 데이터 차트, 분석 아이콘, 현대적인 그래픽 요소가 포함된 디자인이어야 합니다.
        4. 미적 키워드: 'Professional infographic, premium design, clean layout, vector art, 3D icons, high resolution, soft studio lighting'을 포함하세요.
        5. 오직 영어 프롬프트 텍스트만 반환하세요.
        
        [블로그 본문 발췌]
        {content[:3000]}
        """
        
        result = await gemini.generate_text(prompt, temperature=0.7)
        return result.strip()

blog_service = BlogService()



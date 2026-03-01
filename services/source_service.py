import httpx
from bs4 import BeautifulSoup
import os
import re
from typing import Optional, Dict

class SourceService:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def extract_text_from_url(self, url: str) -> Dict[str, str]:
        """URL에서 정보(기사 또는 유튜브 자막) 추출"""
        # 유튜브 URL 체크
        if "youtube.com" in url or "youtu.be" in url:
            return await self.extract_text_from_youtube(url)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=self.headers, follow_redirects=True)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 제목 추출
                title = ""
                title_tag = soup.find('h1') or soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
                
                # 본문 추출 (일반적인 뉴스 사이트 태그들 시도)
                # 불필요한 태그 제거
                for s in soup(['script', 'style', 'nav', 'header', 'footer', 'iframe', 'aside', 'button', 'input']):
                    s.extract()
                
                # 본문 후보 태그들
                content_selectors = [
                    'article', '.article_body', '.article_content', '#articleBody', 
                    '.news_content', '.view_content', '.content_area', 'main'
                ]
                
                content = ""
                for selector in content_selectors:
                    found = soup.select_one(selector)
                    if found:
                        content = found.get_text(separator='\n').strip()
                        break
                
                if not content:
                    # 후보가 없으면 body에서 추출
                    content = soup.body.get_text(separator='\n').strip() if soup.body else ""
                
                # 공백 정리
                content = re.sub(r'\n+', '\n', content)
                content = re.sub(r' +', ' ', content)
                
                return {
                    "title": title or "제목 없음",
                    "content": content,
                    "url": url
                }
        except Exception as e:
            print(f"URL Extraction Error: {e}")
            raise Exception(f"Failed to extract content from URL: {str(e)}")

    async def extract_text_from_youtube(self, url: str) -> Dict[str, str]:
        """유튜브 URL에서 자막(Transcript) 추출"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            # Video ID 추출
            video_id = None
            if "v=" in url:
                video_id = url.split("v=")[1].split("&")[0]
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[1].split("?")[0]
            
            if not video_id:
                 raise Exception("Could not find Video ID in YouTube URL.")

            # 제목 추출을 위해 별도 요청 (또는 간단히 처리)
            title = f"YouTube Video ({video_id})"
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json")
                    if res.status_code == 200:
                        title = res.json().get('title', title)
            except:
                pass

            # 자막 리스트 가져오기
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # 한국어 우선, 없으면 영어, 없으면 첫 번째 자막
            try:
                transcript = transcript_list.find_transcript(['ko', 'en'])
            except:
                transcript = transcript_list.find_transcript(transcript_list._manually_created_transcripts.keys() or transcript_list._generated_transcripts.keys())

            data = transcript.fetch()
            full_text = " ".join([item['text'] for item in data])
            
            return {
                "title": title,
                "content": full_text,
                "url": url
            }
        except Exception as e:
            print(f"YouTube Extraction Error: {e}")
            raise Exception(f"유튜브 서버에서 자막을 가져오지 못했습니다. (자막이 꺼져있을 수 있습니다)")

    def extract_text_from_file(self, file_path: str) -> Dict[str, str]:
        """로컬 파일(TXT)에서 텍스트 추출"""
        try:
            filename = os.path.basename(file_path)
            content = ""
            
            # 인코딩 시도 (utf-8, cp949)
            encodings = ['utf-8', 'cp949', 'euc-kr']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                raise Exception("Failed to read file with supported encodings.")
                
            return {
                "title": filename,
                "content": content,
                "url": None
            }
        except Exception as e:
            print(f"File Extraction Error: {e}")
            raise Exception(f"Failed to extract text from file: {str(e)}")

source_service = SourceService()

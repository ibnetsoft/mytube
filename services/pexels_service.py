import requests
import random
from config import Config

class PexelsService:
    def __init__(self):
        self.api_key = Config.PEXELS_API_KEY
        self.base_url = Config.PEXELS_BASE_URL
        self.headers = {"Authorization": self.api_key}

    def search_videos(self, query: str, per_page: int = 5, orientation: str = "landscape"):
        """
        Pexels API를 사용하여 비디오를 검색합니다.
        
        Args:
            query (str): 검색어 (영어 권장)
            per_page (int): 가져올 비디오 수
            orientation (str): 비디오 방향 (landscape, portrait, square)
            
        Returns:
            list: 비디오 정보 리스트 [{'id', 'url', 'image', 'duration', 'width', 'height', 'video_files'}]
        """
        if not self.api_key:
             print("⚠️ Pexels API Key is missing.")
             return {"error": "Pexels API 키가 설정되지 않았습니다."}

        url = f"{self.base_url}/search"
        params = {
            "query": query,
            "per_page": per_page,
            "orientation": orientation,
            "size": "medium" # 화질/크기 최적화
        }

        try:
            print(f"DEBUG: Searching Pexels for '{query}'...")
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                videos = []
                for v in data.get("videos", []):
                    # 가장 적절한 화질의 MP4 파일 찾기 (HD 720p/1080p 선호)
                    best_file = None
                    files = v.get("video_files", [])
                    
                    # 1. HD 1920x1080 or 1280x720, mp4
                    candidates = [f for f in files if f['file_type'] == 'video/mp4' and f['height'] in [720, 1080]]
                    if candidates:
                        best_file = max(candidates, key=lambda x: x['width']) # 가장 큰 해상도
                    
                    # 2. 없으면 아무 mp4
                    if not best_file:
                        mp4s = [f for f in files if f['file_type'] == 'video/mp4']
                        if mp4s:
                            best_file = mp4s[0]
                    
                    if best_file:
                        videos.append({
                            "id": v["id"],
                            "url": best_file["link"], # 실제 MP4 다운로드/스트리밍 URL
                            "preview_image": v["image"],
                            "duration": v["duration"],
                            "width": v["width"],
                            "height": v["height"],
                            "user": v["user"]["name"],
                            "pexel_url": v["url"]
                        })
                
                return {"status": "ok", "videos": videos}
            
            elif response.status_code == 401:
                return {"status": "error", "error": "Pexels API 키가 유효하지 않습니다."}
            else:
                return {"status": "error", "error": f"API Error: {response.status_code}"}

        except Exception as e:
            print(f"Pexels Search Failed: {e}")
            return {"status": "error", "error": str(e)}

# Singleton Instance
pexels_service = PexelsService()

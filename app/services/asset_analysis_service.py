from abc import ABC, abstractmethod
from typing import Dict, Any

class VisionProvider(ABC):
    @abstractmethod
    def analyze(self, file_name: str, file_type: str, file_url: str) -> Dict[str, Any]:
        pass

class MockVisionProvider(VisionProvider):
    def analyze(self, file_name: str, file_type: str, file_url: str) -> Dict[str, Any]:
        """
        Lightweight mock analysis based on filename hints for QA/Preview purposes.
        """
        fname = file_name.lower()
        
        # Default mock fallback
        analysis = {
            "content_summary": "A generic visual asset.",
            "subjects": ["unknown"],
            "emotion": "neutral",
            "background": "generic",
            "visual_style": "realistic",
            "has_motion": (file_type == "video")
        }
        
        # Simple rule-based mock
        if "sad" in fname or "crying" in fname:
            analysis["emotion"] = "sad"
        elif "happy" in fname or "smile" in fname:
            analysis["emotion"] = "happy"
            
        if "woman" in fname or "female" in fname:
            analysis["subjects"] = ["woman"]
        elif "man" in fname or "male" in fname:
            analysis["subjects"] = ["man"]
            
        if "city" in fname:
            analysis["background"] = "city street"
        elif "nature" in fname or "forest" in fname:
            analysis["background"] = "forest"
            
        if "anime" in fname:
            analysis["visual_style"] = "anime"
            
        return analysis

class GeminiVisionProvider(VisionProvider):
    def analyze(self, file_name: str, file_type: str, file_url: str) -> Dict[str, Any]:
        raise NotImplementedError("GeminiVisionProvider is planned for Phase 2")

class AssetAnalysisService:
    def __init__(self, provider: VisionProvider):
        self.provider = provider
        
    def set_provider(self, provider: VisionProvider):
        self.provider = provider
        
    def analyze_asset(self, file_name: str, file_type: str, file_url: str) -> Dict[str, Any]:
        return self.provider.analyze(file_name, file_type, file_url)

# Default to Mock Provider for now
asset_analysis_service = AssetAnalysisService(MockVisionProvider())

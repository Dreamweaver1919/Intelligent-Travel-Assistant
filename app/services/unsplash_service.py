import logging
from typing import Dict, List, Optional

import requests


logger = logging.getLogger(__name__)


class UnsplashService:
    """Unsplash image service used to enrich attraction cards."""

    def __init__(self, access_key: str = ""):
        self.access_key = access_key
        self.base_url = "https://api.unsplash.com"

    def search_photos(self, query: str, per_page: int = 10) -> List[Dict]:
        if not self.access_key:
            return []

        try:
            response = requests.get(
                f"{self.base_url}/search/photos",
                params={
                    "query": query,
                    "per_page": per_page,
                    "client_id": self.access_key,
                },
                timeout=10,
            )
            response.raise_for_status()

            photos = []
            for result in response.json().get("results", []):
                photos.append(
                    {
                        "url": result["urls"]["regular"],
                        "description": result.get("description", ""),
                        "photographer": result["user"]["name"],
                    }
                )
            return photos
        except Exception as exc:
            logger.warning("搜索图片失败: %s", exc)
            return []

    def get_photo_url(self, query: str) -> Optional[str]:
        photos = self.search_photos(query, per_page=1)
        return photos[0].get("url") if photos else None

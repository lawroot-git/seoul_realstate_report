import logging
import time
import random
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# List of real User-Agents to prevent blocking
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

class NaverLandClient:
    """Client to fetch current real estate listings and complex data from Naver Land API"""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://new.land.naver.com/api"

    def _get_headers(self) -> Dict[str, str]:
        """Generate random browser headers to avoid rate limiting"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://new.land.naver.com/complexes",
            "Origin": "https://new.land.naver.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }

    def fetch_complexes(self, lawd_cd: str) -> List[Dict[str, Any]]:
        """Fetch list of apartment complexes in a region (cortarNo)"""
        cortar_no = f"{lawd_cd}00000"
        url = f"{self.base_url}/regions/complexes"
        params = {
            "cortarNo": cortar_no,
            "realEstateType": "APT",
            "order": "householdCount" # Order by size
        }

        try:
            logger.info(f"Fetching Naver complexes for region: {lawd_cd}")
            response = self.session.get(url, params=params, headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            
            data = response.json()
            complexList = data.get("complexList", [])
            logger.info(f"Found {len(complexList)} complexes in Naver for {lawd_cd}")
            return complexList
        except Exception as e:
            logger.error(f"Error fetching complexes from Naver for {lawd_cd}: {e}")
            return []

    def fetch_articles(self, complex_no: str, trade_type: str = "A1") -> List[Dict[str, Any]]:
        """
        Fetch active listing articles (매물) for a complex
        trade_type: 'A1' (매매/Sale), 'B1' (전세/Jeonse), 'B2' (월세/Rent)
        """
        url = f"{self.base_url}/articles/complex/{complex_no}"
        params = {
            "realEstateType": "APT",
            "tradeType": trade_type,
            "tag": "||||||||",
            "rentPriceMin": "0",
            "rentPriceMax": "900000000",
            "priceMin": "0",
            "priceMax": "900000000",
            "areaMin": "0",
            "areaMax": "900000000",
            "sameAddressGroup": "true", # Group duplicate listings
            "page": "1"
        }

        try:
            # Random delay between requests to be gentle
            time.sleep(random.uniform(0.3, 0.8))
            
            response = self.session.get(url, params=params, headers=self._get_headers(), timeout=15)
            if response.status_code == 429:
                logger.warning(f"Naver Rate Limit (429) hit for complex {complex_no}. Sleeping for 5s...")
                time.sleep(5)
                return []
                
            response.raise_for_status()
            data = response.json()
            
            articles = data.get("articleList", [])
            return articles
        except Exception as e:
            logger.warning(f"Error fetching articles for complex {complex_no}: {e}")
            return []

    def get_complex_details(self, complex_no: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed information about a complex (e.g. household count, approval date)"""
        url = f"{self.base_url}/complexes/{complex_no}"
        
        try:
            time.sleep(random.uniform(0.2, 0.5))
            response = self.session.get(url, headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Error fetching details for complex {complex_no}: {e}")
            return None

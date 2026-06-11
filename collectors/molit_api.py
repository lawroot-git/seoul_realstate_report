import logging
import time
import requests
import xmltodict
import pandas as pd
from typing import List, Dict, Any, Optional
from config.settings import MOLIT_API_KEY

logger = logging.getLogger(__name__)

# Key mapping for unified English column names
FIELD_MAP = {
    # Common
    '아파트': 'apt_name',
    'aptNm': 'apt_name',
    '법정동': 'dong',
    'dong': 'dong',
    'umdNm': 'dong',
    '전용면적': 'exclusive_area',
    'excluUseAr': 'exclusive_area',
    '건축년도': 'build_year',
    'buildYear': 'build_year',
    '년': 'deal_year',
    'dealYear': 'deal_year',
    '월': 'deal_month',
    'dealMonth': 'deal_month',
    '일': 'deal_day',
    'dealDay': 'deal_day',
    '층': 'floor',
    'floor': 'floor',
    '지번': 'jibun',
    'jibun': 'jibun',
    '일련번호': 'serial_number',
    'serialNo': 'serial_number',
    
    # Trade specific
    '거래금액': 'deal_amount',
    'dealAmount': 'deal_amount',
    '거래유형': 'transaction_type',
    'reqGbn': 'transaction_type',
    '중개사소재지': 'broker_location',
    'rdealerLoc': 'broker_location',
    '해제여부': 'cancellation_status',
    'cdealType': 'cancellation_status',
    '해제사유발생일': 'cancellation_date',
    'cdealDay': 'cancellation_date',
    '등기일자': 'registration_date',
    'rgstDate': 'registration_date',

    # Rent specific
    '보증금액': 'deposit',
    'deposit': 'deposit',
    '월세금액': 'monthly_rent',
    'monthlyRent': 'monthly_rent',
}

class MolitApiClient:
    """Client for Ministry of Land, Infrastructure and Transport (MOLIT) Real Estate API"""
    
    def __init__(self, api_key: str = MOLIT_API_KEY):
        self.api_key = api_key
        # Check if we should use newer endpoint or older fallback endpoint
        self.trade_endpoint = "http://openapi.molit.go.kr:8081/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev"
        self.rent_endpoint = "http://openapi.molit.go.kr:8081/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptRentDev"
        
        # New 1613000 endpoints from public portal
        self.new_trade_endpoint = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        self.new_rent_endpoint = "http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

    def _fetch_page(self, url: str, params: Dict[str, Any], max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Fetch raw XML data from API with retries and return as dict"""
        for attempt in range(1, max_retries + 1):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/xml,text/xml,*/*'
                }
                
                logger.info(f"Fetching: {url} (LAWD_CD={params.get('LAWD_CD')}, DEAL_YMD={params.get('DEAL_YMD')}, Page={params.get('pageNo')})")
                
                # Using standard requests.get(url, params=params) allows requests to perform the URL encoding
                # of the Decoding Key dynamically and correctly.
                response = requests.get(url, params=params, headers=headers, timeout=15)
                response.raise_for_status()
                
                # Check if API returned an error message instead of XML
                if "SERVICE_KEY_IS_NOT_REGISTERED" in response.text:
                    logger.error("API Error: SERVICE_KEY_IS_NOT_REGISTERED. Please check if MOLIT_API_KEY in .env is the DECODING key.")
                    return None
                    
                data = xmltodict.parse(response.text)
                
                # Check response header
                header = data.get('response', {}).get('header', {})
                result_code = header.get('resultCode')
                result_msg = header.get('resultMsg')
                
                if result_code in ['00', '000'] or 'NORMAL' in str(result_msg).upper():
                    return data
                else:
                    logger.warning(f"API returned non-zero code {result_code}: {result_msg}. Retrying... ({attempt}/{max_retries})")
            except Exception as e:
                logger.warning(f"Error fetching data: {e}. Retrying... ({attempt}/{max_retries})")
            
            time.sleep(2 * attempt)
        return None

    def _parse_items(self, raw_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse raw XML dict and normalize item keys"""
        if not raw_data:
            return []
            
        body = raw_data.get('response', {}).get('body', {})
        if not body or body.get('totalCount') == '0':
            return []
            
        items_wrapper = body.get('items', {})
        if not items_wrapper:
            return []
            
        items = items_wrapper.get('item', [])
        if isinstance(items, dict):
            items = [items] # Single item returned as dict, convert to list
            
        normalized_items = []
        for item in items:
            normalized = {}
            for k, v in item.items():
                # Strip string whitespace
                val = v.strip() if isinstance(v, str) else v
                # Clean up pricing/area values
                if k in ['거래금액', '보증금액', '월세금액', 'dealAmount', 'deposit', 'monthlyRent'] and isinstance(val, str):
                    val = int(val.replace(',', ''))
                elif k in ['전용면적', 'excluUseAr'] and isinstance(val, str):
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                
                norm_key = FIELD_MAP.get(k, k)
                normalized[norm_key] = val
            normalized_items.append(normalized)
            
        return normalized_items

    def get_sales(self, lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
        """Fetch apartment sales for a specific region and month. Try both standard and Dev endpoints."""
        params = {
            'serviceKey': self.api_key,
            'LAWD_CD': lawd_cd,
            'DEAL_YMD': deal_ymd,
            'numOfRows': '1000',
            'pageNo': '1'
        }
        
        # 1. Try "아파트 매매 실거래가 자료" (getRTMSDataSvcAptTrade)
        data = self._fetch_page(self.new_trade_endpoint, params)
        
        # 2. Fallback to "아파트 매매 실거래가 상세 자료" (getRTMSDataSvcAptTradeDev)
        if not data:
            logger.info("Retrying with 'RTMSDataSvcAptTradeDev' endpoint...")
            dev_endpoint = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
            data = self._fetch_page(dev_endpoint, params)
            
        # 3. Fallback to older legacy XML system
        if not data:
            logger.info("Falling back to legacy trade endpoint...")
            data = self._fetch_page(self.trade_endpoint, params)
            
        items = self._parse_items(data)
        df = pd.DataFrame(items)
        
        if not df.empty:
            df['deal_type'] = '매매'
            df['lawd_cd'] = lawd_cd
            # Convert registration and cancellation columns if they exist
            for col in ['cancellation_status', 'cancellation_date', 'registration_date']:
                if col not in df.columns:
                    df[col] = None
        return df

    def get_rents(self, lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
        """Fetch apartment Jeonse/Rent for a specific region and month"""
        params = {
            'serviceKey': self.api_key,
            'LAWD_CD': lawd_cd,
            'DEAL_YMD': deal_ymd,
            'numOfRows': '1000',
            'pageNo': '1'
        }
        
        # Try new endpoint first, fall back to old if needed
        data = self._fetch_page(self.new_rent_endpoint, params)
        if not data:
            logger.info("Falling back to legacy rent endpoint...")
            data = self._fetch_page(self.rent_endpoint, params)
            
        items = self._parse_items(data)
        df = pd.DataFrame(items)
        
        if not df.empty:
            df['lawd_cd'] = lawd_cd
            # Determine Jeonse or Wolse
            df['monthly_rent'] = df.get('monthly_rent', 0).fillna(0).astype(int)
            df['deal_type'] = df['monthly_rent'].apply(lambda x: '월세' if x > 0 else '전세')
            # Normalize deposit
            if 'deposit' in df.columns:
                df['deposit'] = df['deposit'].fillna(0).astype(int)
        return df

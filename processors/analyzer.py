import logging
import datetime
import pandas as pd
from typing import Dict, Any, List, Optional
from config.settings import TARGET_REGIONS

logger = logging.getLogger(__name__)

def calculate_pyung_price(amount: float, exclusive_area: float) -> float:
    """Calculate price per 3.3㎡ of SUPPLY area (평당가 in 만원) by converting exclusive area using a 1.35x average multiplier (74% efficiency ratio)"""
    if not exclusive_area or exclusive_area <= 0:
        return 0.0
    supply_area = exclusive_area * 1.35  # Convert exclusive area to supply area
    pyung = supply_area / 3.3058
    return amount / pyung

class RealEstateAnalyzer:
    """Analyzes MOLIT transaction data and integrates Naver Land listings"""

    @staticmethod
    def analyze_mom_prices(df_curr: pd.DataFrame, df_prev: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Compare current month average prices and volumes with previous month for each region.
        Returns a dict structured by region: {region_name: {trade_type: {curr_avg, prev_avg, change_pct, count}}}
        """
        analysis = {}
        
        for region_name, lawd_cd in TARGET_REGIONS.items():
            analysis[region_name] = {}
            
            # Filter data for this region
            df_c_reg = df_curr[df_curr['lawd_cd'] == lawd_cd] if not df_curr.empty else pd.DataFrame()
            df_p_reg = df_prev[df_prev['lawd_cd'] == lawd_cd] if not df_prev.empty else pd.DataFrame()
            
            for deal_type in ['매매', '전세', '월세']:
                analysis[region_name][deal_type] = {
                    'curr_avg': 0.0,
                    'curr_pyung_avg': 0.0,
                    'curr_count': 0,
                    'prev_avg': 0.0,
                    'prev_pyung_avg': 0.0,
                    'prev_count': 0,
                    'change_pct': 0.0,
                    'pyung_change_pct': 0.0,
                }
                
                # Current month stats
                df_c_type = df_c_reg[df_c_reg['deal_type'] == deal_type] if not df_c_reg.empty else pd.DataFrame()
                if not df_c_type.empty:
                    # For 월세, we analyze 'deposit' or monthly rent separately, but for now we focus on 'deposit'
                    price_col = 'deposit' if deal_type in ['전세', '월세'] else 'deal_amount'
                    
                    analysis[region_name][deal_type]['curr_avg'] = df_c_type[price_col].mean()
                    analysis[region_name][deal_type]['curr_count'] = len(df_c_type)
                    
                    # Pyung price calculation
                    pyung_prices = df_c_type.apply(lambda r: calculate_pyung_price(r[price_col], r['exclusive_area']), axis=1)
                    analysis[region_name][deal_type]['curr_pyung_avg'] = pyung_prices.mean()

                # Previous month stats
                df_p_type = df_p_reg[df_p_reg['deal_type'] == deal_type] if not df_p_reg.empty else pd.DataFrame()
                if not df_p_type.empty:
                    price_col = 'deposit' if deal_type in ['전세', '월세'] else 'deal_amount'
                    
                    analysis[region_name][deal_type]['prev_avg'] = df_p_type[price_col].mean()
                    analysis[region_name][deal_type]['prev_count'] = len(df_p_type)
                    
                    # Pyung price calculation
                    pyung_prices = df_p_type.apply(lambda r: calculate_pyung_price(r[price_col], r['exclusive_area']), axis=1)
                    analysis[region_name][deal_type]['prev_pyung_avg'] = pyung_prices.mean()

                # Calculate Percentage Changes
                curr_avg = analysis[region_name][deal_type]['curr_avg']
                prev_avg = analysis[region_name][deal_type]['prev_avg']
                if prev_avg > 0 and curr_avg > 0:
                    analysis[region_name][deal_type]['change_pct'] = ((curr_avg - prev_avg) / prev_avg) * 100

                curr_pyung_avg = analysis[region_name][deal_type]['curr_pyung_avg']
                prev_pyung_avg = analysis[region_name][deal_type]['prev_pyung_avg']
                if prev_pyung_avg > 0 and curr_pyung_avg > 0:
                    analysis[region_name][deal_type]['pyung_change_pct'] = ((curr_pyung_avg - prev_pyung_avg) / prev_pyung_avg) * 100

            # Calculate Jeonse Rate (전세가율)
            # Jeonse rate = Avg Jeonse Deposit / Avg Sale Deal Amount * 100
            avg_sale = analysis[region_name]['매매']['curr_avg']
            avg_jeonse = analysis[region_name]['전세']['curr_avg']
            analysis[region_name]['jeonse_rate'] = (avg_jeonse / avg_sale * 100) if avg_sale > 0 else 0.0

        return analysis

    @staticmethod
    def get_area_analysis(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Analyze average sales price by size segments:
        - Small (전용면적 <= 59㎡)
        - Medium (59㎡ < 전용면적 <= 84㎡)
        - Large (전용면적 > 84㎡)
        """
        if df.empty:
            return {}
            
        df_sales = df[df['deal_type'] == '매매']
        if df_sales.empty:
            return {}
            
        def get_segment(area):
            if area <= 59.0:
                return '소형 (59㎡ 이하)'
            elif area <= 84.9:
                return '중형 (60~84㎡)'
            else:
                return '대형 (85㎡ 초과)'

        df_sales = df_sales.copy()
        df_sales['segment'] = df_sales['exclusive_area'].apply(get_segment)
        
        segments = {}
        for name, group in df_sales.groupby('segment'):
            pyung_prices = group.apply(lambda r: calculate_pyung_price(r['deal_amount'], r['exclusive_area']), axis=1)
            segments[name] = {
                'avg_price': group['deal_amount'].mean(),
                'avg_pyung_price': pyung_prices.mean(),
                'count': len(group)
            }
        return segments

    @staticmethod
    def get_top_complexes(df: pd.DataFrame, limit: int = 10) -> List[Dict[str, Any]]:
        """Identify the complexes with the highest transaction volumes in the current month"""
        if df.empty:
            return []
            
        df_sales = df[df['deal_type'] == '매매']
        if df_sales.empty:
            return []
            
        # Group by complex and count
        top_list = []
        gp = df_sales.groupby(['complex_no', 'complex_name', 'dong'])
        
        for (comp_no, comp_name, dong), group in gp:
            pyung_prices = group.apply(lambda r: calculate_pyung_price(r['deal_amount'], r['exclusive_area']), axis=1)
            top_list.append({
                'complex_no': comp_no,
                'complex_name': comp_name,
                'dong': dong,
                'tx_count': len(group),
                'avg_price': group['deal_amount'].mean(),
                'max_price': group['deal_amount'].max(),
                'avg_pyung_price': pyung_prices.mean(),
                'build_year': group['build_year'].iloc[0] if 'build_year' in group.columns else None
            })
            
        # Sort by count desc, then average price desc
        top_list = sorted(top_list, key=lambda x: (-x['tx_count'], -x['avg_price']))
        return top_list[:limit]

    @staticmethod
    def enrich_with_naver_listings(top_complexes: List[Dict[str, Any]], naver_client: Any) -> List[Dict[str, Any]]:
        """
        Enrich top complexes with real-time active asking prices (호가) from Naver Land.
        Fetches current sale (매매) and Jeonse (전세) listings.
        """
        enriched_complexes = []
        for comp in top_complexes:
            comp_no = comp['complex_no']
            comp_copy = comp.copy()
            
            # Default asking price stats
            comp_copy['naver_sale_listings'] = 0
            comp_copy['naver_sale_min_price'] = 0
            comp_copy['naver_sale_avg_price'] = 0.0
            
            comp_copy['naver_jeonse_listings'] = 0
            comp_copy['naver_jeonse_min_price'] = 0
            comp_copy['naver_jeonse_avg_price'] = 0.0

            # If complex_no is UNKNOWN (due to Naver 429 block on complex list cache refresh)
            # do not query Naver API to avoid delays and further 429 warnings.
            if not comp_no or comp_no == 'UNKNOWN':
                enriched_complexes.append(comp_copy)
                continue

            # 1. Fetch Sales active listings (A1)
            sale_listings = naver_client.fetch_articles(comp_no, 'A1')
            if sale_listings:
                prices = []
                for art in sale_listings:
                    price_str = art.get('price1', '0')
                    try:
                        # Price is returned in format like "200,000" or just number
                        prices.append(int(price_str.replace(',', '')))
                    except ValueError:
                        pass
                if prices:
                    comp_copy['naver_sale_listings'] = len(prices)
                    comp_copy['naver_sale_min_price'] = min(prices)
                    comp_copy['naver_sale_avg_price'] = sum(prices) / len(prices)

            # 2. Fetch Jeonse active listings (B1)
            jeonse_listings = naver_client.fetch_articles(comp_no, 'B1')
            if jeonse_listings:
                prices = []
                for art in jeonse_listings:
                    price_str = art.get('price1', '0')
                    try:
                        prices.append(int(price_str.replace(',', '')))
                    except ValueError:
                        pass
                if prices:
                    comp_copy['naver_jeonse_listings'] = len(prices)
                    comp_copy['naver_jeonse_min_price'] = min(prices)
                    comp_copy['naver_jeonse_avg_price'] = sum(prices) / len(prices)

            enriched_complexes.append(comp_copy)
            
        return enriched_complexes

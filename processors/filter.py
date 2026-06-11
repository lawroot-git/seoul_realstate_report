import re
import time
import random
import sqlite3
import logging
import datetime
from typing import List, Dict, Any, Set
from pathlib import Path
from config.settings import DB_PATH, TARGET_REGIONS, FILTER_MIN_HOUSEHOLDS, FILTER_MAX_AGE_YEARS
from collectors.naver_land import NaverLandClient

logger = logging.getLogger(__name__)

def normalize_apt_name(name: str) -> str:
    """Normalize apartment name for robust matching (remove spaces, symbols, brackets)"""
    if not name:
        return ""
    name = str(name).strip()
    # Remove contents inside parentheses e.g. "래미안대치(1단지)" -> "래미안대치"
    name = re.sub(r'\(.*?\)', '', name)
    # Remove spaces and special characters
    name = re.sub(r'[\s_\-\,\.]', '', name)
    return name

class ApartmentFilter:
    """Manages the cache database of target complexes (200+ units, <20 years old)"""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table to store target complexes meeting our criteria
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS target_complexes (
                complex_no TEXT PRIMARY KEY,
                complex_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                dong_name TEXT NOT NULL,
                lawd_cd TEXT NOT NULL,
                total_households INTEGER NOT NULL,
                use_approve_ymd TEXT,
                build_year INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Index for fast lookup by dong and normalized name
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complex_lookup ON target_complexes(dong_name, normalized_name)")
        conn.commit()
        conn.close()

    def refresh_cache_if_needed(self, force: bool = False):
        """
        Pull all complexes from Naver Land, filter them, and save to SQLite DB.
        Updates cache if empty, or if forced.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM target_complexes")
        count = cursor.fetchone()[0]
        
        if count > 0 and not force:
            logger.info(f"Target complexes cache already has {count} entries. Skipping refresh.")
            conn.close()
            return

        logger.info("Refreshing target complexes cache database from Naver Land...")
        client = NaverLandClient()
        current_year = datetime.datetime.now().year
        cutoff_year = current_year - FILTER_MAX_AGE_YEARS

        target_complex_count = 0
        
        for region_name, lawd_cd in TARGET_REGIONS.items():
            complexes = client.fetch_complexes(lawd_cd)
            
            # Insert valid complexes
            for comp in complexes:
                comp_no = comp.get("complexNo")
                comp_name = comp.get("complexName", "")
                dong_name = comp.get("dongName", "")
                households = comp.get("totalHouseholdCount", 0)
                approve_ymd = comp.get("useApproveYmd", "") # Format: e.g. "20151125" or "201511" or ""
                
                # Extract build year
                build_year = None
                if approve_ymd and len(approve_ymd) >= 4:
                    try:
                        build_year = int(approve_ymd[:4])
                    except ValueError:
                        pass
                
                # Fallback: if Naver does not provide approve_ymd in regional list, we check details if needed, 
                # or use whatever is available. If build_year is not available, we temporarily allow it 
                # but will double check during transaction filtering via transaction's build_year.
                
                # Check filtering conditions
                is_large_enough = households >= FILTER_MIN_HOUSEHOLDS
                is_new_enough = build_year is None or build_year >= cutoff_year
                
                if is_large_enough and is_new_enough:
                    norm_name = normalize_apt_name(comp_name)
                    cursor.execute("""
                        INSERT OR REPLACE INTO target_complexes 
                        (complex_no, complex_name, normalized_name, dong_name, lawd_cd, total_households, use_approve_ymd, build_year, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (comp_no, comp_name, norm_name, dong_name, lawd_cd, households, approve_ymd, build_year))
                    target_complex_count += 1
            
            # Avoid hitting rate limits between regions
            time.sleep(random.uniform(1.0, 2.0))

        conn.commit()
        conn.close()
        logger.info(f"Target complexes cache refresh complete. Stored {target_complex_count} qualifying complexes.")

    def get_target_complex_list(self) -> List[Dict[str, Any]]:
        """Retrieve the list of target complexes in database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM target_complexes")
        rows = cursor.fetchall()
        
        result = [dict(row) for row in rows]
        conn.close()
        return result

    def get_complex_mapping(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns a mapping of {(dong, normalized_name): complex_info}
        for high-performance in-memory filtering of real estate transactions.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT complex_no, complex_name, normalized_name, dong_name, total_households, build_year FROM target_complexes")
        rows = cursor.fetchall()
        conn.close()
        
        mapping = {}
        for row in rows:
            key = (row['dong_name'], row['normalized_name'])
            mapping[key] = {
                'complex_no': row['complex_no'],
                'complex_name': row['complex_name'],
                'total_households': row['total_households'],
                'build_year': row['build_year']
            }
        return mapping

    def filter_transactions(self, df_tx: Any) -> Any:
        """
        Filters a transactions DataFrame, keeping only transactions in target complexes
        matching our criteria (200+ units, <20 years built).
        Adds complex info (complex_no, households, normalized_build_year) to the DataFrame.
        """
        if df_tx is None or df_tx.empty:
            return df_tx

        # Get in-memory map of target complexes
        mapping = self.get_complex_mapping()
        
        filtered_rows = []
        current_year = datetime.datetime.now().year
        cutoff_year = current_year - FILTER_MAX_AGE_YEARS

        # FALLBACK: If target complexes cache is completely empty (likely due to Naver API 429 block)
        # proceed with filtering transactions by building age only, so the report still generates!
        if not mapping:
            logger.warning("⚠️ Target complexes database is empty (likely due to Naver Land API 429 block). "
                           "Falling back to filtering transactions by building age (<20 years) ONLY.")
            for idx, row in df_tx.iterrows():
                tx_build_year = row.get('build_year')
                try:
                    tx_build_year = int(tx_build_year) if tx_build_year else None
                except ValueError:
                    tx_build_year = None
                    
                if tx_build_year and tx_build_year < cutoff_year:
                    # Built too long ago
                    continue
                    
                row_dict = row.to_dict()
                row_dict['complex_no'] = 'UNKNOWN'
                row_dict['complex_name'] = row.get('apt_name', '알 수 없음')
                row_dict['total_households'] = 0
                row_dict['build_year'] = tx_build_year
                filtered_rows.append(row_dict)
            import pandas as pd
            return pd.DataFrame(filtered_rows)

        # STANDARD PATH: Filter against SQLite target complexes cache
        for idx, row in df_tx.iterrows():
            dong = str(row.get('dong', '')).strip()
            apt_name = str(row.get('apt_name', '')).strip()
            
            # Transaction build year
            tx_build_year = row.get('build_year')
            try:
                tx_build_year = int(tx_build_year) if tx_build_year else None
            except ValueError:
                tx_build_year = None
                
            norm_name = normalize_apt_name(apt_name)
            
            # Lookup by dong and normalized name
            match = mapping.get((dong, norm_name))
            
            # Perform a fallback fuzzy match if exact normalized name fails (e.g. check if transaction name is in cache name or vice versa)
            if not match:
                for (cache_dong, cache_norm_name), info in mapping.items():
                    if cache_dong == dong and (norm_name in cache_norm_name or cache_norm_name in norm_name):
                        match = info
                        break
            
            if match:
                # Target complex found in our SQLite cache!
                # double check building age from transaction just in case
                final_build_year = tx_build_year or match['build_year']
                if final_build_year and final_build_year < cutoff_year:
                    # Built too long ago
                    continue
                    
                row_dict = row.to_dict()
                row_dict['complex_no'] = match['complex_no']
                row_dict['complex_name'] = match['complex_name']
                row_dict['total_households'] = match['total_households']
                row_dict['build_year'] = final_build_year
                filtered_rows.append(row_dict)
                
        import pandas as pd
        return pd.DataFrame(filtered_rows)

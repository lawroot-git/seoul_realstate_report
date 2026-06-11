import os
import sys
import logging
import datetime
import warnings
import pandas as pd
from pathlib import Path

# Suppress annoying urllib3 OpenSSL/LibreSSL compatibility warnings
warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*")

# Add project root to python path
sys.path.append(str(Path(__file__).resolve().parent))

from config.settings import LOG_FILE, TARGET_REGIONS, DATA_DIR
from collectors.molit_api import MolitApiClient
from collectors.naver_land import NaverLandClient
from processors.filter import ApartmentFilter
from processors.analyzer import RealEstateAnalyzer
from processors.trend import TrendChartGenerator
from reports.generator import ReportGenerator
from delivery.email_sender import EmailSender

# Configure Logging to console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger("SeoulRealEstateReport")

def get_target_months():
    """
    Get current and previous month as strings (YYYYMM).
    If we are early in the month (e.g. before the 10th), current month real transaction data
    might be extremely sparse, so we fallback to the previous month as 'current'
    and 2 months ago as 'previous'.
    """
    today = datetime.datetime.now()
    
    # Calculate months
    curr_date = today
    prev_date = today - datetime.timedelta(days=30)
    
    # If today is early in the month (e.g. day <= 7), shift back by one month
    if today.day <= 7:
        logger.info("Early in the month. Shifting target analysis window back by 1 month for denser data.")
        curr_date = today - datetime.timedelta(days=30)
        prev_date = today - datetime.timedelta(days=60)
        
    curr_ym = curr_date.strftime("%Y%m")
    prev_ym = prev_date.strftime("%Y%m")
    return curr_ym, prev_ym

def main():
    logger.info("==================================================")
    logger.info("🚀 Starting Seoul Real Estate Daily Report System")
    logger.info("==================================================")
    
    try:
        # 1. Initialize and refresh Target Complexes Cache
        apt_filter = ApartmentFilter()
        try:
            apt_filter.refresh_cache_if_needed(force=False)
        except Exception as cache_err:
            logger.warning(f"⚠️ Failed to refresh target complexes cache: {cache_err}. "
                           "The pipeline will proceed using backup age-based filtering.")
        
        # 2. Determine Target Months
        curr_ym, prev_ym = get_target_months()
        logger.info(f"Target Analysis Window: Current Month={curr_ym}, Previous Month={prev_ym}")
        
        # 3. Collect Data from MOLIT API
        molit_client = MolitApiClient()
        
        list_curr_tx = []
        list_prev_tx = []
        
        for gu_name, lawd_cd in TARGET_REGIONS.items():
            logger.info(f"Gathering data for {gu_name} ({lawd_cd})...")
            
            # Current Month Transactions
            try:
                sales_curr = molit_client.get_sales(lawd_cd, curr_ym)
                rents_curr = molit_client.get_rents(lawd_cd, curr_ym)
                
                # Merge current sales & rents
                if not sales_curr.empty:
                    list_curr_tx.append(sales_curr)
                if not rents_curr.empty:
                    list_curr_tx.append(rents_curr)
            except Exception as e:
                logger.error(f"Error fetching current month data for {gu_name}: {e}")

            # Previous Month Transactions
            try:
                sales_prev = molit_client.get_sales(lawd_cd, prev_ym)
                rents_prev = molit_client.get_rents(lawd_cd, prev_ym)
                
                if not sales_prev.empty:
                    list_prev_tx.append(sales_prev)
                if not rents_prev.empty:
                    list_prev_tx.append(rents_prev)
            except Exception as e:
                logger.error(f"Error fetching previous month data for {gu_name}: {e}")

        # Combine all districts
        df_curr_raw = pd.concat(list_curr_tx, ignore_index=True) if list_curr_tx else pd.DataFrame()
        df_prev_raw = pd.concat(list_prev_tx, ignore_index=True) if list_prev_tx else pd.DataFrame()
        
        logger.info(f"Total raw transactions fetched: Current Month={len(df_curr_raw)}, Previous Month={len(df_prev_raw)}")
        
        # 4. Filter Transactions (Targeting 200+ units, <20 years built)
        logger.info("Filtering transactions by criteria (200+ households, <20 years age)...")
        df_curr_filtered = apt_filter.filter_transactions(df_curr_raw)
        df_prev_filtered = apt_filter.filter_transactions(df_prev_raw)
        
        logger.info(f"Filtered transactions: Current Month={len(df_curr_filtered)}, Previous Month={len(df_prev_filtered)}")
        
        if df_curr_filtered.empty:
            logger.error("❌ No transaction data matched the target criteria. Exiting.")
            return
            
        # 5. Run Market Analysis
        logger.info("Analyzing transaction data...")
        gu_analysis = RealEstateAnalyzer.analyze_mom_prices(df_curr_filtered, df_prev_filtered)
        area_analysis = RealEstateAnalyzer.get_area_analysis(df_curr_filtered)
        
        # 6. Excluded Naver Land asking prices crawling (Option B removed as per user request)
        logger.info("Skipping Naver Land active listing enrichment (disabled)...")
        all_transactions_list = df_curr_filtered.to_dict('records')
        
        # 7. Generate Analytical Charts (Trend)
        logger.info("Generating visualization charts...")
        chart_price_b64 = TrendChartGenerator.generate_gu_price_comparison(gu_analysis)
        chart_volume_b64 = TrendChartGenerator.generate_tx_volume_comparison(gu_analysis)
        
        charts = {
            'chart_price': chart_price_b64,
            'chart_volume': chart_volume_b64
        }
        
        # 8. Generate HTML Report
        logger.info("Rendering HTML report...")
        report_gen = ReportGenerator()
        html_content = report_gen.generate_html(
            gu_analysis=gu_analysis,
            area_analysis=area_analysis,
            all_transactions=all_transactions_list
        )
        
        # 9. Save HTML Report to History
        history_dir = DATA_DIR / "history"
        history_dir.mkdir(exist_ok=True)
        
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        report_file_path = history_dir / f"report_{today_str}.html"
        
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"✅ HTML report saved to history: {report_file_path}")
        
        # 10. Send Email
        logger.info("Sending report email...")
        sender = EmailSender()
        send_success = sender.send_report(
            html_content=html_content,
            charts=charts,
            subject=f"서울 주요 7개구 부동산 실거래 동향 일일 보고서 ({curr_ym[:4]}년 {curr_ym[4:]}월 기준)"
        )
        
        if send_success:
            logger.info("🎉 System execution completed successfully!")
        else:
            logger.warning("⚠️ System execution completed, but report email failed to send (check configuration).")
            
    except Exception as e:
        logger.exception(f"❌ Fatal error in report execution pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

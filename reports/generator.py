import logging
import datetime
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any, List
from config.settings import BASE_DIR

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generates the HTML email report by binding parsed data to the Jinja2 template"""

    def __init__(self):
        template_dir = BASE_DIR / "reports" / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    def generate_html(
        self,
        gu_analysis: Dict[str, Any],
        area_analysis: Dict[str, Any],
        all_transactions: List[Dict[str, Any]],
        report_date: str = None
    ) -> str:
        """Render the Jinja2 template with real estate data and return the HTML string"""
        try:
            if not report_date:
                report_date = datetime.datetime.now().strftime("%Y-%m-%d")

            # 1. Load the template
            template = self.env.get_template("email_template.html")

            # 2. Calculate summary/aggregate metrics for the dashboard
            total_tx_count = 0
            total_sum_pyung_price = 0.0
            total_gu_with_pyung = 0
            jeonse_rates = []

            for gu_name, data in gu_analysis.items():
                # Accumulate current sales count
                total_tx_count += data.get('매매', {}).get('curr_count', 0)
                
                # Average pyung price across all gu
                pyung_price = data.get('매매', {}).get('curr_pyung_avg', 0)
                if pyung_price > 0:
                    total_sum_pyung_price += pyung_price
                    total_gu_with_pyung += 1
                
                # Jeonse rates
                j_rate = data.get('jeonse_rate', 0.0)
                if j_rate > 0:
                    jeonse_rates.append(j_rate)

            total_avg_pyung_price = (total_sum_pyung_price / total_gu_with_pyung) if total_gu_with_pyung > 0 else 0.0
            total_avg_jeonse_rate = (sum(jeonse_rates) / len(jeonse_rates)) if jeonse_rates else 0.0

            # Map region codes to Korean names for each transaction
            lawd_to_gu = {
                "11680": "강남구",
                "11650": "서초구",
                "11710": "송파구",
                "11170": "용산구",
                "11200": "성동구",
                "11590": "동작구",
                "11740": "강동구",
            }
            
            # Sort transactions first: Date descending
            sorted_txs = sorted(
                all_transactions,
                key=lambda x: (
                    -int(x.get('deal_year', 0)),
                    -int(x.get('deal_month', 0)),
                    -int(x.get('deal_day', 0))
                )
            )

            # Group transactions by gu_name and deal_type
            grouped_txs = {}
            for gu_name in lawd_to_gu.values():
                grouped_txs[gu_name] = {
                    '매매': [],
                    '전세': [],
                    '월세': []
                }
            
            for tx in sorted_txs:
                gu_name = lawd_to_gu.get(tx.get('lawd_cd', ''), '기타')
                tx['gu_name'] = gu_name
                dtype = tx.get('deal_type')
                if gu_name in grouped_txs and dtype in ['매매', '전세', '월세']:
                    grouped_txs[gu_name][dtype].append(tx)

            # 3. Render template
            html_content = template.render(
                report_date=report_date,
                gu_analysis=gu_analysis,
                area_analysis=area_analysis,
                all_transactions=sorted_txs,
                grouped_transactions=grouped_txs,
                total_tx_count=total_tx_count,
                total_avg_pyung_price=total_avg_pyung_price,
                total_avg_jeonse_rate=total_avg_jeonse_rate
            )

            logger.info("Successfully generated HTML report content.")
            return html_content
        except Exception as e:
            logger.error(f"Error generating HTML report: {e}")
            raise e

    def generate_summary_html(
        self,
        gu_analysis: Dict[str, Any],
        area_analysis: Dict[str, Any],
        all_transactions: List[Dict[str, Any]],
        report_date: str = None
    ) -> str:
        """Render the lightweight summary email template and return the HTML string"""
        try:
            if not report_date:
                report_date = datetime.datetime.now().strftime("%Y-%m-%d")

            template = self.env.get_template("email_summary_template.html")

            total_tx_count = 0
            total_sum_pyung_price = 0.0
            total_gu_with_pyung = 0
            jeonse_rates = []

            for gu_name, data in gu_analysis.items():
                total_tx_count += data.get('매매', {}).get('curr_count', 0)
                pyung_price = data.get('매매', {}).get('curr_pyung_avg', 0)
                if pyung_price > 0:
                    total_sum_pyung_price += pyung_price
                    total_gu_with_pyung += 1
                j_rate = data.get('jeonse_rate', 0.0)
                if j_rate > 0:
                    jeonse_rates.append(j_rate)

            total_avg_pyung_price = (total_sum_pyung_price / total_gu_with_pyung) if total_gu_with_pyung > 0 else 0.0
            total_avg_jeonse_rate = (sum(jeonse_rates) / len(jeonse_rates)) if jeonse_rates else 0.0

            html_content = template.render(
                report_date=report_date,
                gu_analysis=gu_analysis,
                area_analysis=area_analysis,
                total_tx_count=total_tx_count,
                total_avg_pyung_price=total_avg_pyung_price,
                total_avg_jeonse_rate=total_avg_jeonse_rate
            )
            return html_content
        except Exception as e:
            logger.error(f"Error generating summary HTML report: {e}")
            raise e

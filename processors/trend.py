import io
import base64
import logging
from typing import Optional
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

logger = logging.getLogger(__name__)

# Configure matplotlib for Korean characters
# In macOS, 'AppleGothic' is default. In Linux/Ubuntu (like GitHub Actions), we'll try 'NanumGothic' or fallback.
# Let's write a robust font setup.
try:
    # Set style
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # Font setup for Korean support
    mpl.rcParams['axes.unicode_minus'] = False
    
    # Try different Korean fonts in order of availability
    korean_fonts = ['AppleGothic', 'NanumGothic', 'Malgun Gothic', 'DejaVu Sans']
    font_found = False
    for font in korean_fonts:
        try:
            mpl.rcParams['font.family'] = font
            font_found = True
            break
        except:
            pass
            
    if not font_found:
        logger.warning("No designated Korean font found. Chart texts might render as squares if system fonts are missing.")
except Exception as e:
    logger.warning(f"Error setting up matplotlib configuration: {e}")

class TrendChartGenerator:
    """Generates analytical charts for the email report and returns them as Base64 strings"""

    @staticmethod
    def _fig_to_base64(fig) -> str:
        """Convert a matplotlib figure to a Base64-encoded PNG string"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        img_bytes = buf.read()
        buf.close()
        plt.close(fig)
        return base64.b64encode(img_bytes).decode('utf-8')

    @classmethod
    def generate_gu_price_comparison(cls, mom_analysis: dict) -> Optional[str]:
        """
        Generate a bar chart comparing current average sales price across 7 districts
        """
        try:
            regions = list(mom_analysis.keys())
            sale_prices = [mom_analysis[reg]['매매']['curr_pyung_avg'] for reg in regions] # Supply area average pyung price in 만원
            
            # Sort by price desc
            data = sorted(zip(regions, sale_prices), key=lambda x: -x[1])
            sorted_regions, sorted_prices = zip(*data)
            
            fig, ax = plt.subplots(figsize=(7, 4.5))
            
            # Curated gradient-like premium colors (HSL-tailored dark/medium slate blue)
            colors = ['#1e3a8a', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe']
            
            bars = ax.bar(sorted_regions, sorted_prices, color=colors[:len(sorted_regions)], width=0.6, edgecolor='none')
            
            # Formatting
            ax.set_title("서울 주요 구별 아파트 평균 공급평당가 (만원)", fontsize=14, fontweight='bold', pad=15, color='#1f2937')
            ax.set_ylabel("평균 공급평당가 (만원)", fontsize=11, labelpad=10, color='#4b5563')
            ax.grid(axis='y', linestyle='--', alpha=0.5)
            
            # Remove top/right spines
            for spine in ['top', 'right']:
                ax.spines[spine].set_visible(False)
                
            ax.spines['left'].set_color('#d1d5db')
            ax.spines['bottom'].set_color('#d1d5db')
            
            # Add values on top of bars
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.annotate(f"{int(round(height))}만",
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 4),  # 4 points vertical offset
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=9, fontweight='bold', color='#374151')

            plt.tight_layout()
            return cls._fig_to_base64(fig)
        except Exception as e:
            logger.error(f"Error generating comparison chart: {e}")
            return None

    @classmethod
    def generate_tx_volume_comparison(cls, mom_analysis: dict) -> Optional[str]:
        """
        Generate a double-bar chart comparing transaction volume (current vs previous month)
        """
        try:
            regions = list(mom_analysis.keys())
            
            curr_vols = [mom_analysis[reg]['매매']['curr_count'] for reg in regions]
            prev_vols = [mom_analysis[reg]['매매']['prev_count'] for reg in regions]
            
            x = range(len(regions))
            width = 0.35
            
            fig, ax = plt.subplots(figsize=(7, 4.5))
            
            # Premium slate/indigo colors
            bars_prev = ax.bar([i - width/2 for i in x], prev_vols, width, label='전월 매매 거래량', color='#94a3b8')
            bars_curr = ax.bar([i + width/2 for i in x], curr_vols, width, label='당월 매매 거래량', color='#3b82f6')
            
            ax.set_title("서울 주요 구별 매매 거래량 비교 (건)", fontsize=14, fontweight='bold', pad=15, color='#1f2937')
            ax.set_ylabel("거래 건수 (건)", fontsize=11, labelpad=10, color='#4b5563')
            ax.set_xticks(x)
            ax.set_xticklabels(regions)
            ax.legend(frameon=True, facecolor='#f8fafc', edgecolor='none')
            ax.grid(axis='y', linestyle='--', alpha=0.5)
            
            for spine in ['top', 'right']:
                ax.spines[spine].set_visible(False)
                
            ax.spines['left'].set_color('#d1d5db')
            ax.spines['bottom'].set_color('#d1d5db')

            # Add values on top of bars
            for bar in bars_curr:
                height = bar.get_height()
                if height > 0:
                    ax.annotate(f"{height}",
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 2),
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=8, color='#3b82f6', fontweight='bold')
                                
            for bar in bars_prev:
                height = bar.get_height()
                if height > 0:
                    ax.annotate(f"{height}",
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 2),
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=8, color='#64748b')

            plt.tight_layout()
            return cls._fig_to_base64(fig)
        except Exception as e:
            logger.error(f"Error generating volume chart: {e}")
            return None

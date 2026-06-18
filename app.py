import io
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from converter import process, to_csv_bytes

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TikTok Shop SLA Dönüştürücü",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Minimal custom CSS ─────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .metric-card {
        background: #1a1a2e;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/tiktok.png", width=60)
    st.title("TikTok Shop\nSLA Dönüştürücü")
    st.divider()

    st.subheader("⚙️ SLA Ayarları")
    sla_days = st.number_input(
        "SLA Süresi (gün)", min_value=1, max_value=10, value=2,
        help="Ödeme onayından sonra kargoya verilmesi gereken maksimum gün sayısı.",
    )
    business_days_only = st.checkbox(
        "Sadece iş günlerini say", value=True,
        help="Cumartesi ve Pazar günlerini SLA hesabına dahil etmez.",
    )

    st.divider()
    st.subheader("🔍 Filtreler")

    ALL_STATUSES = [
        "Zamanında ✅",
        "Geç Kargolama ⚠️",
        "SLA İhlali ❌",
        "Risk Altında ⚠️",
        "Kargoya Bekleniyor 🕐",
        "İptal / İade",
        "Bilinmiyor",
    ]

    filter_status = st.multiselect(
        "SLA Durumu",
        options=ALL_STATUSES,
        default=[],
        placeholder="Tümünü göster",
    )

    st.divider()
    st.caption("v1.0 · Streamlit Community Cloud")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("## 🛍️ TikTok Shop SLA CSV Dönüştürücü")
st.markdown(
    "TikTok Shop sipariş CSV'nizi yükleyin → SLA analizi otomatik hesaplanır → "
    "Dönüştürülmüş dosyayı indirin."
)
st.divider()

# ── Upload ─────────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "📂 CSV dosyasını buraya sürükleyin veya seçin",
    type=["csv"],
    help="TikTok Shop yönetim panelinden dışa aktarılan sipariş CSV dosyası.",
)

# ── Sample format helper ───────────────────────────────────────────────────────
with st.expander("📋 Örnek CSV formatı & desteklenen sütunlar"):
    st.markdown(
        """
**Zorunlu sütunlar** (en az biri olmalı):
| Sütun | TikTok adı | Açıklama |
|---|---|---|
| Sipariş No | `Order ID` | Benzersiz sipariş kimliği |
| Sipariş Durumu | `Order Status` | Shipped, Cancelled vb. |
| Ödeme Zamanı | `Payment Time` | SLA başlangıç tarihi |
| Son Kargo Tarihi | `Ship By Date` | TikTok'un belirlediği son tarih *(yoksa hesaplanır)* |
| Kargo Tarihi | `Shipped Time` | Gerçek kargolama tarihi |

Türkçe veya İngilizce sütun isimleri otomatik eşleştirilir.
Kodlama (UTF-8, UTF-8-BOM, Windows-1254) otomatik algılanır.
        """
    )
    sample_df = pd.DataFrame(
        {
            "Order ID": ["TT-001", "TT-002", "TT-003", "TT-004"],
            "Order Status": ["Shipped", "Awaiting Shipment", "Shipped", "Cancelled"],
            "Payment Time": [
                "2024-03-10 09:00:00",
                "2024-03-10 14:00:00",
                "2024-03-09 11:00:00",
                "2024-03-08 16:00:00",
            ],
            "Ship By Date": [
                "2024-03-12 23:59:59",
                "2024-03-12 23:59:59",
                "2024-03-11 23:59:59",
                "2024-03-10 23:59:59",
            ],
            "Shipped Time": ["2024-03-11 10:00:00", "", "2024-03-12 15:00:00", ""],
            "Product Name": ["Ürün A", "Ürün B", "Ürün C", "Ürün D"],
        }
    )
    st.dataframe(sample_df, use_container_width=True, hide_index=True)

    sample_csv = to_csv_bytes(sample_df)
    st.download_button(
        "⬇️ Örnek CSV'yi indir",
        data=sample_csv,
        file_name="ornek_siparis.csv",
        mime="text/csv",
    )

# ── Main processing ────────────────────────────────────────────────────────────
if uploaded_file is None:
    st.info("👆 Başlamak için bir CSV dosyası yükleyin.")
    st.stop()

with st.spinner("CSV işleniyor..."):
    try:
        df_result, summary, col_map = process(
            uploaded_file,
            sla_days=int(sla_days),
            business_days_only=business_days_only,
        )
    except Exception as exc:
        st.error(f"❌ Dosya işlenirken hata oluştu: {exc}")
        st.stop()

if df_result.empty:
    st.warning("CSV dosyası boş veya okunamadı.")
    st.stop()

# ── Column mapping info ────────────────────────────────────────────────────────
if col_map:
    with st.expander("🔗 Algılanan sütun eşleşmeleri"):
        pairs = [(k, v) for k, v in col_map.items()]
        info_df = pd.DataFrame(pairs, columns=["Standart Alan", "CSV Sütunu"])
        st.dataframe(info_df, hide_index=True, use_container_width=True)
else:
    st.warning(
        "Hiçbir standart sütun eşleşmedi. CSV'niz beklenen sütun isimlerini içermiyor olabilir."
    )

st.divider()

# ── Metrics ────────────────────────────────────────────────────────────────────
st.subheader("📊 Özet")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Toplam Sipariş", summary.get("total", 0))
m2.metric("Zamanında ✅", summary.get("on_time", 0))
m3.metric("SLA İhlali ❌", summary.get("breach", 0))
m4.metric("Risk / Geç ⚠️", summary.get("at_risk", 0))
m5.metric(
    "Uyum Oranı",
    f"{summary.get('compliance_rate', 0):.1f}%",
    help="İptal/iade siparişler hariç zamanında kargolamanın yüzdesi.",
)

st.divider()

# ── Charts ─────────────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns([1, 2])

with chart_col1:
    st.subheader("Durum Dağılımı")
    by_status = summary.get("by_status", {})
    if by_status:
        STATUS_COLORS = {
            "Zamanında ✅": "#2ecc71",
            "Geç Kargolama ⚠️": "#f39c12",
            "SLA İhlali ❌": "#e74c3c",
            "Risk Altında ⚠️": "#e67e22",
            "Kargoya Bekleniyor 🕐": "#3498db",
            "İptal / İade": "#95a5a6",
            "Bilinmiyor": "#bdc3c7",
        }
        fig_pie = px.pie(
            names=list(by_status.keys()),
            values=list(by_status.values()),
            color=list(by_status.keys()),
            color_discrete_map=STATUS_COLORS,
            hole=0.4,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)

with chart_col2:
    st.subheader("Günlük Sipariş & SLA İhlali Trendi")
    pay_col = col_map.get("payment_time")
    if pay_col and pay_col in df_result.columns:
        trend_df = df_result[[pay_col, "SLA Durumu"]].copy()
        trend_df["Tarih"] = pd.to_datetime(trend_df[pay_col], errors="coerce").dt.date
        trend_df = trend_df.dropna(subset=["Tarih"])

        daily = (
            trend_df.groupby(["Tarih", "SLA Durumu"])
            .size()
            .reset_index(name="Adet")
        )
        if not daily.empty:
            fig_bar = px.bar(
                daily,
                x="Tarih",
                y="Adet",
                color="SLA Durumu",
                color_discrete_map={
                    "Zamanında ✅": "#2ecc71",
                    "Geç Kargolama ⚠️": "#f39c12",
                    "SLA İhlali ❌": "#e74c3c",
                    "Risk Altında ⚠️": "#e67e22",
                    "Kargoya Bekleniyor 🕐": "#3498db",
                    "İptal / İade": "#95a5a6",
                    "Bilinmiyor": "#bdc3c7",
                },
                barmode="stack",
            )
            fig_bar.update_layout(margin=dict(t=0, b=0), legend_title="SLA Durumu")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Tarih verisi bulunamadı.")
    else:
        st.info("Ödeme tarihi sütunu algılanamadı, trend grafiği gösterilemiyor.")

st.divider()

# ── Data table ────────────────────────────────────────────────────────────────
st.subheader("📋 Sipariş Listesi")

display_df = df_result.copy()
if filter_status:
    display_df = display_df[display_df["SLA Durumu"].isin(filter_status)]

st.caption(f"{len(display_df)} / {len(df_result)} sipariş gösteriliyor")

STATUS_BG = {
    "Zamanında ✅": "background-color: #d4edda; color: #155724",
    "Geç Kargolama ⚠️": "background-color: #fff3cd; color: #856404",
    "SLA İhlali ❌": "background-color: #f8d7da; color: #721c24",
    "Risk Altında ⚠️": "background-color: #ffe5b4; color: #7d4e00",
    "Kargoya Bekleniyor 🕐": "background-color: #cce5ff; color: #004085",
    "İptal / İade": "background-color: #e2e3e5; color: #383d41",
}


def _highlight(val):
    return STATUS_BG.get(val, "")


if "SLA Durumu" in display_df.columns:
    styled = display_df.style.map(_highlight, subset=["SLA Durumu"])
    st.dataframe(styled, use_container_width=True, height=420, hide_index=True)
else:
    st.dataframe(display_df, use_container_width=True, height=420, hide_index=True)

st.divider()

# ── Download ──────────────────────────────────────────────────────────────────
st.subheader("⬇️ Dönüştürülmüş CSV'yi İndir")

dl_col1, dl_col2 = st.columns([2, 1])
with dl_col1:
    include_only_sla = st.checkbox(
        "Sadece SLA ihlali ve risk siparişlerini indir",
        value=False,
    )

download_df = df_result.copy()
if include_only_sla and "SLA Durumu" in download_df.columns:
    download_df = download_df[
        download_df["SLA Durumu"].isin(["SLA İhlali ❌", "Risk Altında ⚠️", "Geç Kargolama ⚠️"])
    ]

with dl_col2:
    st.metric("İndirilecek satır", len(download_df))

csv_bytes = to_csv_bytes(download_df)
base_name = uploaded_file.name.rsplit(".", 1)[0]
st.download_button(
    label=f"📥 {base_name}_sla.csv olarak indir",
    data=csv_bytes,
    file_name=f"{base_name}_sla.csv",
    mime="text/csv",
    use_container_width=True,
)

import io
import pandas as pd
import streamlit as st
import plotly.express as px

from converter import (
    process, load_file, map_columns, to_tiktok_format,
    get_unknown_carriers, normalize_carrier,
    CARRIER_DISPLAY_LIST, CARRIER_MAP, to_csv_bytes,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TikTok Shop SLA Dönüştürücü",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    "<style>div[data-testid='stMetricValue']{font-size:2rem}</style>",
    unsafe_allow_html=True,
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/tiktok.png", width=60)
    st.title("TikTok Shop\nSLA Dönüştürücü")
    st.divider()

    st.subheader("⚙️ SLA Ayarları")
    sla_days = st.number_input("SLA Süresi (gün)", min_value=1, max_value=10, value=2)
    business_days_only = st.checkbox("Sadece iş günlerini say", value=True)

    st.divider()
    st.subheader("🔍 Filtreler")
    ALL_STATUSES = [
        "Zamanında ✅", "Geç Kargolama ⚠️", "SLA İhlali ❌",
        "Risk Altında ⚠️", "Kargoya Bekleniyor 🕐", "İptal / İade", "Bilinmiyor",
    ]
    filter_status = st.multiselect("SLA Durumu", options=ALL_STATUSES, default=[], placeholder="Tümünü göster")

    st.divider()
    st.caption("v2.0 · Streamlit Community Cloud")

# ── Header + tabs ──────────────────────────────────────────────────────────────
st.markdown("## 🛍️ TikTok Shop SLA Dönüştürücü")
tab_sla, tab_convert = st.tabs(["📊 SLA Analizi", "🔄 TikTok Format Dönüştür"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SLA ANALİZİ
# ══════════════════════════════════════════════════════════════════════════════
with tab_sla:
    st.markdown(
        "TikTok Shop sipariş CSV/Excel'inizi yükleyin → SLA analizi otomatik hesaplanır → "
        "Dönüştürülmüş dosyayı indirin."
    )

    uploaded_sla = st.file_uploader(
        "📂 Sipariş dosyasını yükleyin (CSV veya Excel)",
        type=["csv", "xlsx", "xls"],
        key="sla_upload",
    )

    with st.expander("📋 Desteklenen sütunlar"):
        st.markdown(
            """
| Alan | Örnek sütun adları |
|---|---|
| Sipariş No | `Order ID`, `Sipariş No` |
| Sipariş Durumu | `Order Status`, `Sipariş Durumu` |
| Ödeme Zamanı | `Payment Time`, `Ödeme Tarihi` |
| Son Kargo Tarihi | `Ship By Date`, `Son Kargo Tarihi` |
| Kargo Tarihi | `Shipped Time`, `Kargo Tarihi` |

CSV, XLSX ve XLS desteklenir. UTF-8, UTF-8-BOM, Windows-1254 kodlamaları otomatik algılanır.
            """
        )

    if uploaded_sla is None:
        st.info("👆 Başlamak için bir dosya yükleyin.")
        st.stop()

    with st.spinner("İşleniyor..."):
        try:
            df_result, summary, col_map = process(
                uploaded_sla, uploaded_sla.name,
                sla_days=int(sla_days), business_days_only=business_days_only,
            )
        except Exception as exc:
            st.error(f"❌ Hata: {exc}")
            st.stop()

    if df_result.empty:
        st.warning("Dosya boş veya okunamadı.")
        st.stop()

    if col_map:
        with st.expander("🔗 Algılanan sütun eşleşmeleri"):
            st.dataframe(
                pd.DataFrame(col_map.items(), columns=["Standart Alan", "CSV Sütunu"]),
                hide_index=True, use_container_width=True,
            )

    st.divider()

    # Metrics
    st.subheader("📊 Özet")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Toplam Sipariş",  summary.get("total", 0))
    m2.metric("Zamanında ✅",    summary.get("on_time", 0))
    m3.metric("SLA İhlali ❌",   summary.get("breach", 0))
    m4.metric("Risk / Geç ⚠️",  summary.get("at_risk", 0))
    m5.metric("Uyum Oranı",      f"{summary.get('compliance_rate', 0):.1f}%")

    st.divider()

    # Charts
    c1, c2 = st.columns([1, 2])
    STATUS_COLORS = {
        "Zamanında ✅":        "#2ecc71",
        "Geç Kargolama ⚠️":   "#f39c12",
        "SLA İhlali ❌":       "#e74c3c",
        "Risk Altında ⚠️":    "#e67e22",
        "Kargoya Bekleniyor 🕐": "#3498db",
        "İptal / İade":        "#95a5a6",
        "Bilinmiyor":          "#bdc3c7",
    }
    with c1:
        st.subheader("Durum Dağılımı")
        by_status = summary.get("by_status", {})
        if by_status:
            fig = px.pie(
                names=list(by_status.keys()), values=list(by_status.values()),
                color=list(by_status.keys()), color_discrete_map=STATUS_COLORS, hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Günlük Sipariş & SLA İhlali Trendi")
        pay_col = col_map.get("payment_time")
        if pay_col and pay_col in df_result.columns:
            trend = df_result[[pay_col, "SLA Durumu"]].copy()
            trend["Tarih"] = pd.to_datetime(trend[pay_col], errors="coerce").dt.date
            trend = trend.dropna(subset=["Tarih"])
            daily = trend.groupby(["Tarih", "SLA Durumu"]).size().reset_index(name="Adet")
            if not daily.empty:
                fig2 = px.bar(
                    daily, x="Tarih", y="Adet", color="SLA Durumu",
                    color_discrete_map=STATUS_COLORS, barmode="stack",
                )
                fig2.update_layout(margin=dict(t=0, b=0), legend_title="SLA Durumu")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Ödeme tarihi sütunu algılanamadı.")

    st.divider()

    # Table
    st.subheader("📋 Sipariş Listesi")
    display_df = df_result.copy()
    if filter_status:
        display_df = display_df[display_df["SLA Durumu"].isin(filter_status)]
    st.caption(f"{len(display_df)} / {len(df_result)} sipariş")

    STATUS_BG = {
        "Zamanında ✅":        "background-color:#d4edda;color:#155724",
        "Geç Kargolama ⚠️":   "background-color:#fff3cd;color:#856404",
        "SLA İhlali ❌":       "background-color:#f8d7da;color:#721c24",
        "Risk Altında ⚠️":    "background-color:#ffe5b4;color:#7d4e00",
        "Kargoya Bekleniyor 🕐": "background-color:#cce5ff;color:#004085",
        "İptal / İade":        "background-color:#e2e3e5;color:#383d41",
    }

    if "SLA Durumu" in display_df.columns:
        st.dataframe(
            display_df.style.map(lambda v: STATUS_BG.get(v, ""), subset=["SLA Durumu"]),
            use_container_width=True, height=420, hide_index=True,
        )
    else:
        st.dataframe(display_df, use_container_width=True, height=420, hide_index=True)

    st.divider()

    # Download
    st.subheader("⬇️ Dönüştürülmüş CSV'yi İndir")
    dl_col1, dl_col2 = st.columns([2, 1])
    with dl_col1:
        only_breach = st.checkbox("Sadece SLA ihlali ve risk siparişlerini indir")
    dl_df = df_result.copy()
    if only_breach and "SLA Durumu" in dl_df.columns:
        dl_df = dl_df[dl_df["SLA Durumu"].isin(["SLA İhlali ❌", "Risk Altında ⚠️", "Geç Kargolama ⚠️"])]
    with dl_col2:
        st.metric("İndirilecek satır", len(dl_df))
    base = uploaded_sla.name.rsplit(".", 1)[0]
    st.download_button(
        f"📥 {base}_sla.csv olarak indir",
        data=to_csv_bytes(dl_df),
        file_name=f"{base}_sla.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TİKTOK FORMAT DÖNÜŞTÜRÜCÜsü
# ══════════════════════════════════════════════════════════════════════════════
with tab_convert:
    st.markdown(
        "Depo/fulfillment sisteminden dışa aktardığınız CSV/Excel dosyasını yükleyin → "
        "Sütunlar ve carrier'lar otomatik eşleştirilir → "
        "TikTok Seller Center'a yüklenmeye hazır CSV indirin."
    )

    with st.expander("📋 TikTok'un gerektirdiği 3 alan"):
        st.markdown(
            """
| Alan | Açıklama |
|---|---|
| `order_id` | TikTok sipariş numarası |
| `tracking_number` | Kargo takip numarası |
| `shipping_provider_id` | TikTok'un sayısal carrier ID'si (otomatik eşleştirilir) |

> **Not:** `shipping_provider_id` değerlerini TikTok Seller Center → Orders → Bulk Upload Tracking şablonundan doğrulayın.
            """
        )

    uploaded_conv = st.file_uploader(
        "📂 Depo CSV / Excel dosyasını yükleyin",
        type=["csv", "xlsx", "xls"],
        key="conv_upload",
    )

    if uploaded_conv is None:
        st.info("👆 Başlamak için depo sisteminizden dışa aktardığınız CSV/Excel dosyasını yükleyin.")
        st.stop()

    # Load
    with st.spinner("Dosya okunuyor..."):
        try:
            raw_df = load_file(uploaded_conv, uploaded_conv.name)
            col_map_conv = map_columns(raw_df)
        except Exception as exc:
            st.error(f"❌ Hata: {exc}")
            st.stop()

    st.success(f"✅ {len(raw_df)} satır okundu · {len(raw_df.columns)} sütun")

    st.divider()

    # ── Sütun eşleştirme ──────────────────────────────────────────────────────
    st.subheader("1️⃣ Sütun Eşleştirmesi")
    st.caption("Otomatik eşleştirme yapıldı. Yanlış sütun varsa düzeltebilirsiniz.")

    all_cols   = ["(boş)"] + list(raw_df.columns)
    targets    = ["order_id", "tracking_number", "shipping_provider"]
    labels     = {"order_id": "Order ID", "tracking_number": "Tracking Number", "shipping_provider": "Carrier / Kargo Firması"}
    final_map  = {}

    col_a, col_b, col_c = st.columns(3)
    for field, col_widget in zip(targets, [col_a, col_b, col_c]):
        auto = col_map_conv.get(field, "(boş)")
        if auto not in all_cols:
            auto = "(boş)"
        chosen = col_widget.selectbox(
            labels[field],
            options=all_cols,
            index=all_cols.index(auto),
            key=f"col_{field}",
        )
        if chosen != "(boş)":
            final_map[field] = chosen

    missing_required = [f for f in ["order_id", "tracking_number"] if f not in final_map]
    if missing_required:
        st.warning(f"⚠️ Zorunlu alan eşleşmedi: {', '.join(missing_required)}")

    st.divider()

    # ── Carrier eşleştirme ─────────────────────────────────────────────────────
    st.subheader("2️⃣ Carrier Eşleştirmesi")

    carrier_col_name = final_map.get("shipping_provider")
    carrier_overrides: dict = {}

    if not carrier_col_name:
        st.info("Carrier sütunu seçilmedi — shipping_provider_id boş bırakılacak.")
    else:
        unknown_carriers = get_unknown_carriers(raw_df, carrier_col_name)

        if not unknown_carriers:
            st.success("✅ Tüm carrier'lar otomatik eşleştirildi.")
        else:
            st.warning(f"**{len(unknown_carriers)} bilinmeyen carrier** — aşağıdan manuel seçin:")
            for uc in unknown_carriers:
                chosen_display = st.selectbox(
                    f"`{uc}` → TikTok Carrier",
                    options=["(eşleştirme yok)"] + CARRIER_DISPLAY_LIST,
                    key=f"carrier_{uc}",
                )
                if chosen_display != "(eşleştirme yok)":
                    pid = next(
                        (v["id"] for v in CARRIER_MAP.values() if v["display"] == chosen_display),
                        None,
                    )
                    if pid is not None:
                        carrier_overrides[uc] = pid

        # Preview auto-matched carriers
        with st.expander("🔍 Otomatik eşleşen carrier'ları gör"):
            preview_rows = []
            for val in raw_df[carrier_col_name].dropna().unique():
                pid, display = normalize_carrier(str(val))
                if pid is not None:
                    preview_rows.append({"CSV'deki değer": val, "TikTok Carrier": display, "ID": pid})
            if preview_rows:
                st.dataframe(pd.DataFrame(preview_rows), hide_index=True, use_container_width=True)
            else:
                st.info("Otomatik eşleşen carrier yok.")

    st.divider()

    # ── Dönüştür ──────────────────────────────────────────────────────────────
    st.subheader("3️⃣ Dönüştür & İndir")

    if st.button("🔄 TikTok Formatına Dönüştür", type="primary", use_container_width=True):
        with st.spinner("Dönüştürülüyor..."):
            valid_df, error_df = to_tiktok_format(raw_df, final_map, carrier_overrides)

        total    = len(raw_df)
        valid_n  = len(valid_df)
        error_n  = len(error_df)

        r1, r2, r3 = st.columns(3)
        r1.metric("Toplam Satır",       total)
        r2.metric("Geçerli ✅",          valid_n)
        r3.metric("Hatalı / Atlanan ❌", error_n)

        if valid_n > 0:
            st.success(f"✅ {valid_n} satır TikTok formatına dönüştürüldü.")
            st.dataframe(valid_df.head(20), hide_index=True, use_container_width=True)
            base = uploaded_conv.name.rsplit(".", 1)[0]
            st.download_button(
                f"📥 {base}_tiktok.csv olarak indir",
                data=to_csv_bytes(valid_df),
                file_name=f"{base}_tiktok.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.error("Geçerli satır üretilemedi. Sütun eşleştirmelerini kontrol edin.")

        if error_n > 0:
            with st.expander(f"❌ {error_n} hatalı satırı gör"):
                st.dataframe(
                    error_df[["order_id", "tracking_number", "_raw_carrier", "_errors"]],
                    hide_index=True, use_container_width=True,
                )
                st.download_button(
                    "⬇️ Hatalı satırları indir",
                    data=to_csv_bytes(error_df),
                    file_name=f"{base}_hatalar.csv",
                    mime="text/csv",
                )

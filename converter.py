import io
import chardet
import pandas as pd
from datetime import datetime, timedelta
from fuzzywuzzy import process as fuzz_process

# ── Column alias mapping ───────────────────────────────────────────────────────
COLUMN_ALIASES = {
    "order_id": [
        "Order ID", "order_id", "Sipariş No", "siparis_no",
        "Order Number", "Sipariş Numarası", "TikTok Order ID",
    ],
    "order_status": [
        "Order Status", "order_status", "Sipariş Durumu", "Status", "Durum",
    ],
    "payment_time": [
        "Payment Time", "payment_time", "Ödeme Zamanı", "Ödeme Tarihi",
        "Payment Date", "Paid Time",
    ],
    "ship_by_date": [
        "Ship By Date", "ship_by_date", "Son Kargo Tarihi",
        "Kargo Son Tarihi", "Ship-by Date", "Latest Ship Time",
    ],
    "shipped_time": [
        "Shipped Time", "shipped_time", "Kargo Tarihi",
        "Kargoya Verilen Tarih", "Shipped Date", "Ship Time",
    ],
    "tracking_number": [
        "Tracking Number", "tracking_number", "Takip No",
        "Takip Numarası", "Waybill Number", "Tracking #", "Tracking No",
    ],
    "product_name": [
        "Product Name", "product_name", "Ürün Adı", "Urun Adi", "Item Name",
    ],
    "sku": ["SKU ID", "SKU", "sku", "Ürün Kodu", "Seller SKU"],
    "quantity": ["Quantity", "quantity", "Adet", "Miktar", "Qty"],
    "buyer_paid": [
        "Buyer Paid", "buyer_paid", "Alıcı Ödedi",
        "Toplam Tutar", "Order Total",
    ],
    "shipping_provider": [
        "Shipping Provider Name", "shipping_provider", "Kargo Firması",
        "Kargo Şirketi", "Logistics Provider", "Carrier", "Carrier Name",
        "Kargo", "Kargo Adı",
    ],
    "buyer_username": [
        "Buyer Username", "buyer_username", "Alıcı", "Buyer",
    ],
    "cancel_reason": [
        "Cancel Reason", "cancel_reason", "İptal Nedeni", "Cancellation Reason",
    ],
}

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
]

CANCELLED_KEYWORDS = ["cancel", "iptal", "refund", "iade", "returned"]
SHIPPED_KEYWORDS   = ["shipped", "kargolan", "delivered", "teslim", "completed"]

# ── TikTok Carrier Map  (carrier name → TikTok shipping_provider_id) ──────────
# ID'leri TikTok Seller Center > Orders > Bulk Upload Tracking > şablonundan doğrulayın.
CARRIER_MAP: dict[str, dict] = {
    # US
    "ups":                          {"id": 1,   "display": "UPS"},
    "united parcel service":        {"id": 1,   "display": "UPS"},
    "usps":                         {"id": 2,   "display": "USPS"},
    "united states postal service": {"id": 2,   "display": "USPS"},
    "fedex":                        {"id": 3,   "display": "FedEx"},
    "federal express":              {"id": 3,   "display": "FedEx"},
    "dhl":                          {"id": 4,   "display": "DHL"},
    "dhl express":                  {"id": 4,   "display": "DHL"},
    "ontrac":                       {"id": 5,   "display": "OnTrac"},
    "lasership":                    {"id": 6,   "display": "LaserShip / LSO"},
    "lso":                          {"id": 6,   "display": "LaserShip / LSO"},
    "amazon":                       {"id": 7,   "display": "Amazon Logistics"},
    "amazon logistics":             {"id": 7,   "display": "Amazon Logistics"},
    "pilot freight":                {"id": 8,   "display": "Pilot Freight Services"},
    "spee-dee":                     {"id": 9,   "display": "Spee-Dee Delivery"},
    "better trucks":                {"id": 10,  "display": "Better Trucks"},
    "lone star overnight":          {"id": 11,  "display": "Lone Star Overnight"},
    "golden state overnight":       {"id": 12,  "display": "Golden State Overnight"},
    "seko":                         {"id": 13,  "display": "SEKO Logistics"},
    "veho":                         {"id": 14,  "display": "Veho"},
    "axlehire":                     {"id": 15,  "display": "AxleHire"},
    "maergo":                       {"id": 16,  "display": "Maergo"},
    "jingdong":                     {"id": 17,  "display": "JD Logistics"},
    "jd logistics":                 {"id": 17,  "display": "JD Logistics"},
    "ceva":                         {"id": 18,  "display": "CEVA Logistics"},
    "tforce":                       {"id": 19,  "display": "TForce Freight"},
    "uds":                          {"id": 20,  "display": "UDS"},
    "pandion":                      {"id": 21,  "display": "Pandion"},
    "sf express":                   {"id": 22,  "display": "SF Express"},
    "yto":                          {"id": 23,  "display": "YTO Express"},
    "sto":                          {"id": 24,  "display": "STO Express"},
    "zto":                          {"id": 25,  "display": "ZTO Express"},
    "ems":                          {"id": 26,  "display": "EMS"},
    # TR
    "yurtici":                      {"id": 200, "display": "Yurtiçi Kargo"},
    "yurtiçi":                      {"id": 200, "display": "Yurtiçi Kargo"},
    "yurtici kargo":                {"id": 200, "display": "Yurtiçi Kargo"},
    "yurtiçi kargo":                {"id": 200, "display": "Yurtiçi Kargo"},
    "mng":                          {"id": 201, "display": "MNG Kargo"},
    "mng kargo":                    {"id": 201, "display": "MNG Kargo"},
    "aras":                         {"id": 202, "display": "Aras Kargo"},
    "aras kargo":                   {"id": 202, "display": "Aras Kargo"},
    "ptt":                          {"id": 203, "display": "PTT Kargo"},
    "ptt kargo":                    {"id": 203, "display": "PTT Kargo"},
    "surat":                        {"id": 204, "display": "Sürat Kargo"},
    "sürat":                        {"id": 204, "display": "Sürat Kargo"},
    "surat kargo":                  {"id": 204, "display": "Sürat Kargo"},
    "sürat kargo":                  {"id": 204, "display": "Sürat Kargo"},
    "trendyol express":             {"id": 205, "display": "Trendyol Express"},
    "hepsijet":                     {"id": 206, "display": "HepsiJet"},
    "sendeo":                       {"id": 207, "display": "Sendeo"},
    "kargoist":                     {"id": 208, "display": "Kargoist"},
    "borusan":                      {"id": 209, "display": "Borusan Lojistik"},
    "horoz":                        {"id": 210, "display": "Horoz Lojistik"},
    "ceva lojistik":                {"id": 211, "display": "CEVA Lojistik"},
    "tnt":                          {"id": 212, "display": "TNT"},
    # EU / Global
    "hermes":                       {"id": 300, "display": "Hermes"},
    "dpd":                          {"id": 301, "display": "DPD"},
    "gls":                          {"id": 302, "display": "GLS"},
    "dhl parcel":                   {"id": 303, "display": "DHL Parcel"},
    "royal mail":                   {"id": 304, "display": "Royal Mail"},
    "evri":                         {"id": 305, "display": "Evri"},
    "postnl":                       {"id": 306, "display": "PostNL"},
    "colissimo":                    {"id": 307, "display": "Colissimo"},
    "correos":                      {"id": 308, "display": "Correos"},
    "bpost":                        {"id": 309, "display": "bpost"},
    "colis prive":                  {"id": 310, "display": "Colis Privé"},
    "yunexpress":                   {"id": 311, "display": "Yun Express"},
    "4px":                          {"id": 312, "display": "4PX"},
}

CARRIER_DISPLAY_LIST = sorted({v["display"] for v in CARRIER_MAP.values()})


# ── File loading ───────────────────────────────────────────────────────────────

def _detect_encoding(raw: bytes) -> str:
    return chardet.detect(raw).get("encoding") or "utf-8"


def _detect_delimiter(text: str) -> str:
    first = text.split("\n")[0]
    best, best_n = ",", first.count(",")
    for d in [";", "\t", "|"]:
        n = first.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def load_csv(file_obj) -> pd.DataFrame:
    raw = file_obj.read() if hasattr(file_obj, "read") else file_obj
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    encoding = _detect_encoding(raw)
    text = None
    for enc in [encoding, "utf-8-sig", "utf-8", "cp1254", "latin-1"]:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        raise ValueError("Dosya kodlaması çözümlenemedi.")

    df = pd.read_csv(io.StringIO(text), sep=_detect_delimiter(text), dtype=str)
    df.columns = df.columns.str.strip()
    return df.dropna(how="all").reset_index(drop=True)


def load_excel(file_obj) -> pd.DataFrame:
    df = pd.read_excel(file_obj, dtype=str)
    df.columns = df.columns.str.strip()
    return df.dropna(how="all").reset_index(drop=True)


def load_file(file_obj, filename: str) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xls"):
        return load_excel(file_obj)
    return load_csv(file_obj)


# ── Column mapping (alias + fuzzy) ────────────────────────────────────────────

def map_columns(df: pd.DataFrame, fuzzy_threshold: int = 72) -> dict:
    col_lower  = {c.lower().strip(): c for c in df.columns}
    mapping    = {}
    used_cols  = set()  # prevent same CSV column being mapped twice

    for standard, aliases in COLUMN_ALIASES.items():
        # Exact alias match first
        for alias in aliases:
            orig = None
            if alias in df.columns:
                orig = alias
            elif alias.lower() in col_lower:
                orig = col_lower[alias.lower()]
            if orig and orig not in used_cols:
                mapping[standard] = orig
                used_cols.add(orig)
                break
        if standard in mapping:
            continue

        # Fuzzy match against unmapped columns
        remaining = [c for c in df.columns if c not in used_cols]
        if not remaining:
            continue
        result = fuzz_process.extractOne(standard.replace("_", " "), remaining)
        if result and result[1] >= fuzzy_threshold:
            mapping[standard] = result[0]
            used_cols.add(result[0])

    return mapping


# ── Date parsing ───────────────────────────────────────────────────────────────

def _parse_dates(series: pd.Series) -> pd.Series:
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        if parsed.notna().sum() > 0:
            return parsed
    return pd.to_datetime(series, errors="coerce", infer_datetime_format=True)


# ── Business days ──────────────────────────────────────────────────────────────

def _add_business_days(start: datetime, days: int) -> datetime:
    if pd.isna(start):
        return pd.NaT
    current, added = start, 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


# ── SLA calculation ────────────────────────────────────────────────────────────

def calculate_sla(
    df: pd.DataFrame,
    col_map: dict,
    sla_days: int = 2,
    business_days_only: bool = True,
) -> pd.DataFrame:
    result = df.copy()
    now = datetime.now()

    pay_col  = col_map.get("payment_time")
    ship_col = col_map.get("shipped_time")
    sbd_col  = col_map.get("ship_by_date")
    status_col = col_map.get("order_status")

    payment_time = _parse_dates(result[pay_col])  if pay_col  else pd.Series([pd.NaT] * len(result))
    shipped_time = _parse_dates(result[ship_col]) if ship_col else pd.Series([pd.NaT] * len(result))

    if sbd_col:
        ship_by_date = _parse_dates(result[sbd_col])
    elif pay_col:
        if business_days_only:
            ship_by_date = payment_time.apply(
                lambda x: _add_business_days(x, sla_days) if pd.notna(x) else pd.NaT
            )
        else:
            ship_by_date = payment_time + timedelta(days=sla_days)
    else:
        ship_by_date = pd.Series([pd.NaT] * len(result))

    result["__payment_time"] = payment_time
    result["__shipped_time"] = shipped_time
    result["__ship_by_date"] = ship_by_date

    def _status(row):
        raw_status = str(row.get(status_col, "")).lower() if status_col else ""
        if any(k in raw_status for k in CANCELLED_KEYWORDS):
            return "İptal / İade"
        sbd = row["__ship_by_date"]
        st  = row["__shipped_time"]
        if pd.notna(st):
            return "Zamanında ✅" if pd.isna(sbd) or st <= sbd else "Geç Kargolama ⚠️"
        if pd.isna(sbd):
            return "Bilinmiyor"
        remaining_h = (sbd - now).total_seconds() / 3600
        if remaining_h < 0:
            return "SLA İhlali ❌"
        if remaining_h < 24:
            return "Risk Altında ⚠️"
        return "Kargoya Bekleniyor 🕐"

    result["SLA Durumu"] = result.apply(_status, axis=1)
    result["Son Kargo Tarihi"] = result["__ship_by_date"].apply(
        lambda x: x.strftime("%d/%m/%Y %H:%M") if pd.notna(x) else "-"
    )

    def _diff(row):
        sbd = row["__ship_by_date"]
        st  = row["__shipped_time"]
        if pd.isna(sbd):
            return None
        ref = st if pd.notna(st) else now
        return round((sbd - ref).total_seconds() / 86400, 1)

    result["SLA Farkı (Gün)"] = result.apply(_diff, axis=1)
    return result.drop(columns=["__payment_time", "__shipped_time", "__ship_by_date"])


def get_summary(df: pd.DataFrame) -> dict:
    if "SLA Durumu" not in df.columns:
        return {}
    counts    = df["SLA Durumu"].value_counts().to_dict()
    total     = len(df)
    cancelled = sum(v for k, v in counts.items() if "İptal"      in k)
    on_time   = sum(v for k, v in counts.items() if "Zamanında"  in k)
    breach    = sum(v for k, v in counts.items() if "İhlali"     in k)
    at_risk   = sum(v for k, v in counts.items() if "Risk"       in k or "Geç" in k)
    active    = total - cancelled
    return {
        "total": total,
        "on_time": on_time,
        "breach": breach,
        "at_risk": at_risk,
        "cancelled": cancelled,
        "compliance_rate": round(on_time / active * 100, 1) if active else 0.0,
        "by_status": counts,
    }


# ── Carrier normalization ──────────────────────────────────────────────────────

def normalize_carrier(raw: str, threshold: int = 75) -> tuple:
    """Return (shipping_provider_id, display_name). id=None if unknown."""
    if not raw or pd.isna(raw):
        return None, ""
    key = str(raw).lower().strip()
    if key in CARRIER_MAP:
        info = CARRIER_MAP[key]
        return info["id"], info["display"]
    result = fuzz_process.extractOne(key, list(CARRIER_MAP.keys()))
    if result and result[1] >= threshold:
        info = CARRIER_MAP[result[0]]
        return info["id"], info["display"]
    return None, str(raw)


def get_unknown_carriers(df: pd.DataFrame, carrier_col: str) -> list:
    """Return list of unique carrier values that couldn't be mapped."""
    unknowns = []
    for val in df[carrier_col].dropna().unique():
        pid, _ = normalize_carrier(val)
        if pid is None and str(val).strip():
            unknowns.append(str(val).strip())
    return sorted(set(unknowns))


# ── TikTok format output ───────────────────────────────────────────────────────

def to_tiktok_format(
    df: pd.DataFrame,
    col_map: dict,
    carrier_overrides: dict | None = None,
) -> tuple:
    """
    Convert warehouse CSV to TikTok Seller Center bulk-upload format.
    Returns (valid_df, error_df).
    TikTok requires: order_id, tracking_number, shipping_provider_id
    """
    order_col    = col_map.get("order_id")
    tracking_col = col_map.get("tracking_number")
    carrier_col  = col_map.get("shipping_provider")

    rows = []
    for _, row in df.iterrows():
        order_id  = str(row.get(order_col,    "")).strip() if order_col    else ""
        tracking  = str(row.get(tracking_col, "")).strip() if tracking_col else ""
        carrier_r = str(row.get(carrier_col,  "")).strip() if carrier_col  else ""

        errs = []
        if not order_id or order_id == "nan":
            errs.append("Order ID eksik")
        if not tracking or tracking == "nan":
            errs.append("Tracking No eksik")

        # Carrier resolution: user override > auto map
        if carrier_overrides and carrier_r in carrier_overrides:
            provider_id = carrier_overrides[carrier_r]
            provider_display = next(
                (v["display"] for v in CARRIER_MAP.values() if v["id"] == provider_id),
                str(provider_id),
            )
        else:
            provider_id, provider_display = normalize_carrier(carrier_r)

        if provider_id is None:
            errs.append(f"Bilinmeyen carrier: '{carrier_r}'")

        rows.append({
            "order_id":             order_id,
            "tracking_number":      tracking,
            "shipping_provider_id": provider_id if provider_id is not None else "",
            "_carrier_display":     provider_display,
            "_raw_carrier":         carrier_r,
            "_errors":              "; ".join(errs),
            "_valid":               len(errs) == 0,
        })

    full = pd.DataFrame(rows)
    valid = full[full["_valid"]].drop(
        columns=["_errors", "_valid", "_carrier_display", "_raw_carrier"]
    ).reset_index(drop=True)
    errors = full[~full["_valid"]].reset_index(drop=True)
    return valid, errors


# ── Helpers ────────────────────────────────────────────────────────────────────

def process(file_obj, filename: str = "upload.csv", sla_days: int = 2, business_days_only: bool = True):
    df = load_file(file_obj, filename)
    col_map = map_columns(df)
    df_result = calculate_sla(df, col_map, sla_days=sla_days, business_days_only=business_days_only)
    summary = get_summary(df_result)
    return df_result, summary, col_map


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return out.getvalue()

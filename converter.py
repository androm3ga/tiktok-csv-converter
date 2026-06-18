import io
import chardet
import pandas as pd
from datetime import datetime, timedelta


COLUMN_ALIASES = {
    "order_id": [
        "Order ID", "order_id", "Sipariş No", "siparis_no",
        "Order Number", "Sipariş Numarası",
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
        "Takip Numarası", "Waybill Number",
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
        "Shipping Provider Name", "shipping_provider",
        "Kargo Firması", "Kargo Şirketi", "Logistics Provider",
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

CANCELLED_KEYWORDS = ["cancel", "iptal", "refund", "iade", "returned", "iade edildi"]
SHIPPED_KEYWORDS = ["shipped", "kargolan", "delivered", "teslim", "completed", "tamamland"]


def _detect_encoding(raw: bytes) -> str:
    result = chardet.detect(raw)
    return result.get("encoding") or "utf-8"


def _detect_delimiter(text: str) -> str:
    first_line = text.split("\n")[0]
    best = ","
    best_count = first_line.count(",")
    for delim in [";", "\t", "|"]:
        if first_line.count(delim) > best_count:
            best = delim
            best_count = first_line.count(delim)
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

    delimiter = _detect_delimiter(text)
    df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str)
    df.columns = df.columns.str.strip()
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def map_columns(df: pd.DataFrame) -> dict:
    col_lower = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    for standard, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                mapping[standard] = alias
                break
            if alias.lower() in col_lower:
                mapping[standard] = col_lower[alias.lower()]
                break
    return mapping


def _parse_dates(series: pd.Series) -> pd.Series:
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        if parsed.notna().sum() > 0:
            return parsed
    return pd.to_datetime(series, errors="coerce", infer_datetime_format=True)


def _add_business_days(start: datetime, days: int) -> datetime:
    if pd.isna(start):
        return pd.NaT
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def calculate_sla(
    df: pd.DataFrame,
    col_map: dict,
    sla_days: int = 2,
    business_days_only: bool = True,
) -> pd.DataFrame:
    result = df.copy()
    now = datetime.now()

    pay_col = col_map.get("payment_time")
    ship_col = col_map.get("shipped_time")
    sbd_col = col_map.get("ship_by_date")
    status_col = col_map.get("order_status")

    payment_time = _parse_dates(result[pay_col]) if pay_col else pd.Series([pd.NaT] * len(result))
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
        st = row["__shipped_time"]

        if pd.notna(st):
            if pd.isna(sbd) or st <= sbd:
                return "Zamanında ✅"
            return "Geç Kargolama ⚠️"

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

    def _sla_diff(row):
        sbd = row["__ship_by_date"]
        st = row["__shipped_time"]
        if pd.isna(sbd):
            return None
        ref = st if pd.notna(st) else now
        return round((sbd - ref).total_seconds() / 86400, 1)

    result["SLA Farkı (Gün)"] = result.apply(_sla_diff, axis=1)

    result = result.drop(columns=["__payment_time", "__shipped_time", "__ship_by_date"])
    return result


def get_summary(df: pd.DataFrame) -> dict:
    if "SLA Durumu" not in df.columns:
        return {}

    counts = df["SLA Durumu"].value_counts().to_dict()
    total = len(df)
    cancelled = sum(v for k, v in counts.items() if "İptal" in k)
    on_time = sum(v for k, v in counts.items() if "Zamanında" in k)
    breach = sum(v for k, v in counts.items() if "İhlali" in k)
    at_risk = sum(v for k, v in counts.items() if "Risk" in k or "Geç" in k)
    pending = sum(v for k, v in counts.items() if "Bekleniyor" in k)
    active = total - cancelled
    compliance = round(on_time / active * 100, 1) if active > 0 else 0.0

    return {
        "total": total,
        "on_time": on_time,
        "breach": breach,
        "at_risk": at_risk,
        "pending": pending,
        "cancelled": cancelled,
        "compliance_rate": compliance,
        "by_status": counts,
    }


def process(file_obj, sla_days: int = 2, business_days_only: bool = True):
    df = load_csv(file_obj)
    col_map = map_columns(df)
    df_result = calculate_sla(df, col_map, sla_days=sla_days, business_days_only=business_days_only)
    summary = get_summary(df_result)
    return df_result, summary, col_map


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    return output.getvalue()

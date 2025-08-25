# Rentelo Breakdown Assist — Streamlit + Google Sheets
# ----------------------------------------------------
# How this works:
# - Stores all breakdown records in a single Google Sheet tab named "breakdowns"
# - Uses a Google Cloud service account (JSON) via Streamlit Secrets
# - Supports: add breakdowns, update status, assign follow-ups, resolve with timestamp,
#   filter (date, status, type, priority, execs), export CSV, and download printable "cards" PDF
#
# Quick setup (also see README.md):
# 1) Create a Google Cloud "Service Account" and download its JSON key.
# 2) Create a Google Sheet; copy its Sheet ID (the long ID in the URL).
# 3) Share the sheet with the service account's email (Editor permission).
# 4) In Streamlit Cloud -> App -> Settings -> Secrets, paste contents like sample_secrets.toml.
# 5) Deploy!
#
# Author: Built for Rentelo by ChatGPT

import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from datetime import datetime, date
import pytz
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import re

# ------------- CONFIG -------------
st.set_page_config(
    page_title="Rentelo Breakdown Assist",
    page_icon="🛠️",
    layout="wide"
)

INDIA_TZ = pytz.timezone("Asia/Kolkata")

# ------------- GOOGLE SHEETS AUTH -------------
# Secrets structure expected (see sample_secrets.toml in repo/zip):
# [gcp_service_account]
# type = "..."
# project_id = "..."
# private_key_id = "..."
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "..."
# client_id = "..."
# auth_uri = "..."
# token_uri = "..."
# auth_provider_x509_cert_url = "..."
# client_x509_cert_url = "..."
#
# [gsheet]
# sheet_id = "your-google-sheet-id"

if "gcp_service_account" not in st.secrets or "gsheet" not in st.secrets:
    st.error("Secrets not set. Please configure Streamlit secrets as shown in README.md / sample_secrets.toml.")
    st.stop()

SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]
GSHEET_ID = st.secrets["gsheet"]["sheet_id"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)
client = gspread.authorize(credentials)

def get_or_create_worksheet(sheet_id: str, name: str, headers: list):
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=2000, cols=len(headers)+2)
        ws.append_row(headers, value_input_option="USER_ENTERED")
    # Ensure header row matches (non-destructive)
    try:
        existing = ws.row_values(1)
        if existing != headers:
            # Attempt to set header row if different length or content
            ws.resize(rows=ws.row_count, cols=max(len(headers), ws.col_count))
            ws.delete_rows(1)
            ws.insert_row(headers, 1)
    except Exception:
        pass
    return ws

HEADERS = [
    "id","created_at","last_updated",
    "booking_id","customer_name","customer_mobile","pickup_location","booking_days",
    "issue","vehicle_number","vehicle_model","vehicle_type",
    "customer_location_url","latitude","longitude",
    "priority","status","followup_by","added_by","resolved_by","resolved_at"
]

ws = get_or_create_worksheet(GSHEET_ID, "breakdowns", HEADERS)

# ------------- DATA ACCESS LAYER -------------

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=HEADERS)
    df = pd.DataFrame(values[1:], columns=values[0])  # Skip header
    # Normalize dtypes
    if not df.empty:
        for col in ["created_at","last_updated","resolved_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for col in ["booking_days"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        df = pd.DataFrame(columns=HEADERS)
    return df

def now_ts():
    return datetime.now(INDIA_TZ).strftime("%Y-%m-%d %H:%M:%S%z")

def ensure_float(x):
    try:
        return float(x)
    except Exception:
        return None

def extract_lat_lon_from_url(url: str):
    if not url:
        return None, None
    # Match patterns like @12.34,77.12 or q=12.34,77.12
    at = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    q = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if at:
        return float(at.group(1)), float(at.group(2))
    if q:
        return float(q.group(1)), float(q.group(2))
    return None, None

def add_record(record: dict):
    ws.append_row([str(record.get(h, "") or "") for h in HEADERS], value_input_option="USER_ENTERED")


def update_record(row_index: int, record: dict):
    # row_index is 0-based for DataFrame; in Sheets it's +2 (header + 1)
    sheet_row = row_index + 2
    # Ensure all values are strings (avoid Timestamp serialization error)
    row_vals = [str(record.get(h, "") or "") for h in HEADERS]
    ws.update(
        f"A{sheet_row}:{chr(ord('A') + len(HEADERS) - 1)}{sheet_row}",
        [row_vals],
        value_input_option="USER_ENTERED"
    )

def generate_id(booking_id: str):
    # Take last 5 digits of booking_id if it's long
    suffix = booking_id[-5:] if len(booking_id) >= 5 else booking_id
    return f"BD-{suffix}"

# ------------- USER CONTROLS (Top of Page instead of Sidebar) -------------
st.header("🛠️ Rentelo Breakdown Assist")
st.caption("Record, track & resolve vehicle breakdowns.")

# User name input
user_name = st.text_input(
    "Your Name (appears as Added By / Resolved By)",
    value=st.session_state.get("user_name",""),
    placeholder="Search by Name"
)
if user_name:
    st.session_state["user_name"] = user_name
    parts = [p.strip()[0:1].upper() for p in user_name.split() if p.strip()]
    st.session_state["user_initials"] = "".join(parts)[0:2] if parts else "XX"

# Refresh button
if st.button("🔄 Refresh data (from Google Sheet)"):
    st.cache_data.clear()

df = load_data()

st.markdown("---")

# ----------- SEARCH BY BREAKDOWN ID -----------
search_id = st.text_input("🔍 Search by Breakdown ID", placeholder="Enter Breakdown ID (e.g., BD-1001)")

if search_id:
    match = df[df["id"].astype(str).str.strip().str.lower() == search_id.strip().lower()]
    if not match.empty:
        st.success(f"✅ Breakdown ID {search_id} found")
        st.subheader("📋 Breakdown Details")
        st.dataframe(match, use_container_width=True)
    else:
        st.error(f"❌ No breakdown found with ID: {search_id}")


# ------------- MAIN LAYOUT -------------

st.title("Rentelo Breakdown Assist")
st.write("Store & manage scooty/car breakdowns with live data in Google Sheets. Filter, update status, and export.")

tabs = st.tabs(["📑 Breakdown Details", "➕ Change Status", "📋 Manage / Resolve", "🔎 Filter & Export"])


# ------------- TAB: ADD -------------
with tabs[0]:
    st.subheader("Add a new breakdown")
    with st.form("add_form", clear_on_submit=True):
        left, right = st.columns(2)
        with left:
            booking_id = st.text_input("Booking ID *")
            customer_name = st.text_input("Customer Name *")
            customer_mobile = st.text_input("Customer Mobile *")
            pickup_location = st.text_input("Pickup Location")
            booking_days = st.number_input("Booking for days", min_value=0, value=0, step=1)
            vehicle_type = st.selectbox("Vehicle Type *", ["Bike","Car"])
            vehicle_number = st.text_input("Vehicle Number")
            vehicle_model = st.text_input("Vehicle Model")

        with right:
            issue = st.text_area("Issue / Description *", height=120)
            customer_location_url = st.text_input("Customer Location (Google Maps URL)")
            col_lat, col_lon = st.columns(2)
            with col_lat:
                latitude = st.text_input("Latitude (optional)")
            with col_lon:
                longitude = st.text_input("Longitude (optional)")

            priority = st.selectbox("Priority", ["Low","Medium","High","Critical"], index=1)
            followup_by = st.text_input("Follow-up by (Executive)")

        added_by = user_name or st.text_input("Added By", placeholder="Your name")
        status = st.selectbox("Status", ["Open","In Progress","Resolved","Cancelled"], index=0)

        submitted = st.form_submit_button("✅ Submit Breakdown", use_container_width=True)
        if submitted:
            if not booking_id or not customer_mobile or not issue or not vehicle_type:
                st.error("Please fill required fields: Booking ID, Customer Mobile, Issue, Vehicle Type.")
            else:
                # If lat/lon empty but URL provided, try extract
                lat = ensure_float(latitude) if latitude else None
                lon = ensure_float(longitude) if longitude else None
                if (lat is None or lon is None) and customer_location_url:
                    lat2, lon2 = extract_lat_lon_from_url(customer_location_url)
                    lat = lat if lat is not None else lat2
                    lon = lon if lon is not None else lon2
                # Generate breakdown ID based on booking_id
                breakdown_id = generate_id(booking_id)

                record = {
                    "id": breakdown_id,
                    "created_at": now_ts(),
                    "last_updated": now_ts(),
                    "booking_id": booking_id.strip(),
                    "customer_name": customer_name.strip(),
                    "customer_mobile": customer_mobile.strip(),
                    "pickup_location": pickup_location.strip(),
                    "booking_days": booking_days,
                    "issue": issue.strip(),
                    "vehicle_number": vehicle_number.strip(),
                    "vehicle_model": vehicle_model.strip(),
                    "vehicle_type": vehicle_type,
                    "customer_location_url": customer_location_url.strip(),
                    "latitude": lat if lat is not None else "",
                    "longitude": lon if lon is not None else "",
                    "priority": priority,
                    "status": status,
                    "followup_by": followup_by.strip(),
                    "added_by": added_by.strip(),
                    "resolved_by": user_name if status == "Resolved" and user_name else "",
                    "resolved_at": now_ts() if status == "Resolved" else ""
                }
                add_record(record)
                st.success(f"Breakdown added with ID: {record['id']}")
                st.cache_data.clear()

# ------------- TAB: BREAKDOWN DETAILS -------------
with tabs[0]:
    st.subheader("📑 Breakdown Details (All Customers)")

    if df.empty:
        st.info("No breakdown records yet.")
    else:
        # Show most recent first
        df_sorted = df.sort_values(by="created_at", ascending=False, na_position="last").reset_index(drop=True)

        for idx, row in df_sorted.iterrows():
            with st.expander(f"🔧 {row['id']} — {row['customer_name']} ({row['vehicle_type']} {row['vehicle_model']})"):
                st.write(f"**Booking ID:** {row['booking_id']}")
                st.write(f"**Customer Name:** {row['customer_name']}")
                st.write(f"**Mobile:** {row['customer_mobile']}")
                st.write(f"**Pickup Location:** {row['pickup_location']}")
                st.write(f"**Booking Days:** {row['booking_days']}")
                st.write(f"**Issue:** {row['issue']}")
                st.write(f"**Vehicle Number:** {row['vehicle_number']}")
                st.write(f"**Priority:** {row['priority']}")
                st.write(f"**Status:** {row['status']}")

                # Show resolved stamp if already resolved
                # Show resolved stamp if already resolved
                if row['status'] == "Resolved":
                    st.success(f"✅ Resolved by {row.get('resolved_by','')} on {row.get('resolved_at','')}")
                else:
                    # Input field for Resolved By (always rendered)
                    resolved_by_input = st.text_input(
                        f"Resolved By (for {row['id']})",
                        key=f"resolved_by_{idx}"
                    )

                    # Mark as resolved button
                    if st.button(f"Mark {row['id']} as Resolved", key=f"resolve_{idx}"):
                        if not resolved_by_input:
                            st.warning("⚠️ Please enter who resolved this before marking as resolved.")
                        else:
                            updated = row.to_dict()
                            updated["status"] = "Resolved"
                            updated["resolved_by"] = resolved_by_input
                            updated["resolved_at"] = now_ts()
                            updated["last_updated"] = now_ts()
                            update_record(idx, updated)
                            st.success(f"Breakdown {row['id']} marked as Resolved ✅")
                            st.cache_data.clear()
                            st.rerun()




# ------------- TAB: MANAGE / RESOLVE -------------
with tabs[1]:
    st.subheader("Update status / resolve breakdown")
    if df.empty:
        st.info("No breakdowns yet. Add one first.")
    else:
        # Most recent first
        df_sorted = df.sort_values(by="created_at", ascending=False, na_position="last").reset_index(drop=True)
        selected_id = st.selectbox("Select Breakdown ID", options=df_sorted["id"].tolist())
        idx = df_sorted.index[df_sorted["id"] == selected_id][0]
        row = df_sorted.loc[idx].to_dict()

        st.markdown(f"**Booking:** {row.get('booking_id','')} | **Issue:** {row.get('issue','')[:90]}")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            allowed_status = ["Open", "In Progress", "Resolved", "Cancelled"]
            current_status = row.get("status", "Open")
            # If invalid value in sheet, fallback to "Open"
            if current_status not in allowed_status:
                current_status = "Open"
            new_status = st.selectbox("Status", allowed_status, index=allowed_status.index(current_status))
        with c2:
            new_follow = st.text_input("Follow-up by", value=row.get("followup_by",""))
        with c3:
            allowed_priority = ["Low","Medium","High","Critical"]
            current_priority = row.get("priority", "Medium")
            if current_priority not in allowed_priority:
                current_priority = "Medium"
            new_priority = st.selectbox("Priority", allowed_priority, index=allowed_priority.index(current_priority))
        with c4:
            resolved_by = st.text_input("Resolved by", value=row.get("resolved_by","") or (user_name or ""))

        if new_status == "Resolved" and not resolved_by:
            st.warning("Please specify who resolved it.")

        # Location preview
        map_lat = row.get("latitude","")
        map_lon = row.get("longitude","")
        try:
            latf = float(map_lat) if map_lat else None
            lonf = float(map_lon) if map_lon else None
        except Exception:
            latf, lonf = None, None
        if latf is None or lonf is None:
            lat2, lon2 = extract_lat_lon_from_url(row.get("customer_location_url","") or "")
            latf = latf if latf is not None else lat2
            lonf = lonf if lonf is not None else lon2

        if latf is not None and lonf is not None:
            st.map(pd.DataFrame({"lat":[latf],"lon":[lonf]}))

        if st.button("💾 Update", use_container_width=True):
            # Find original row index in df (not df_sorted) by id
            orig_idx_list = df.index[df["id"] == selected_id].tolist()
            if not orig_idx_list:
                st.error("Could not find the original row to update.")
            else:
                orig_idx = orig_idx_list[0]
                updated = df.loc[orig_idx].to_dict()
                updated["status"] = new_status
                updated["followup_by"] = new_follow
                updated["priority"] = new_priority
                updated["last_updated"] = now_ts()

                if new_status == "Resolved":
                    updated["resolved_by"] = resolved_by or (user_name or updated.get("resolved_by",""))
                    if not updated.get("resolved_at"):
                        updated["resolved_at"] = now_ts()
                else:
                    # If moving away from Resolved, clear resolved fields
                    updated["resolved_by"] = "" if new_status != "Resolved" else updated.get("resolved_by","")
                    updated["resolved_at"] = "" if new_status != "Resolved" else updated.get("resolved_at","")

                update_record(orig_idx, updated)
                st.success("Record updated.")
                st.cache_data.clear()


# ------------- TAB: FILTER & EXPORT -------------
with tabs[2]:
    st.subheader("Filter breakdowns & export")

    if df.empty:
        st.info("No data yet.")
    else:
        # Basic filters
        colB, colC, colD = st.columns(3)
        with colB:
            status_filter = st.multiselect(
                "Status",
                options=["Open", "In Progress", "Resolved", "Cancelled"],
                default=[],
                placeholder="Select status"
            )
        with colC:
            prio_filter = st.multiselect(
                "Priority",
                options=["Low", "Medium", "High", "Critical"],
                default=[],
                placeholder="Select priority"
            )
        with colD:
            exec_filter = st.text_input("Follow-up by contains", "")

        filtered = df.copy()
        if status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]
        if prio_filter:
            filtered = filtered[filtered["priority"].isin(prio_filter)]
        if exec_filter:
            filtered = filtered[filtered["followup_by"].str.contains(exec_filter, case=False, na=False)]

        # Date filter on created_at
        start_date = st.date_input("Start Date", value=date.today().replace(day=1))
        end_date = st.date_input("End Date", value=date.today())
        filtered["created_at"] = pd.to_datetime(filtered["created_at"], errors="coerce")
        mask = (filtered["created_at"].dt.date >= start_date) & (filtered["created_at"].dt.date <= end_date)
        filtered = filtered[mask].sort_values(by="created_at", ascending=False, na_position="last")

        st.dataframe(filtered, use_container_width=True, height=400)

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download CSV", data=csv, file_name="breakdowns_filtered.csv", mime="text/csv")


# ------------- TAB: DOWNLOAD CARDS -------------
with tabs[3]:
    st.subheader("📇 Download Breakdown Cards")

    # Filters
    pick_status = st.multiselect(
        "Include Status",
        ["Open", "In Progress", "Resolved", "Cancelled"],
        default=[],
        placeholder="Select status"
    )
    pick_type = st.multiselect(
        "Include Type",
        ["Bike", "Car"],
        default=[],
        placeholder="Select type"
    )

    many = df.copy()

    # Apply filters only if user selected something
    if pick_status:
        many = many[many["status"].isin(pick_status)]
    if pick_type:
        many = many[many["vehicle_type"].isin(pick_type)]

    many["created_at"] = pd.to_datetime(many["created_at"], errors="coerce")
    many = many.sort_values(by="created_at", ascending=False, na_position="last")

    # Card generator
    def card(row):
        return f"""
        Booking ID: {row.get('booking_id','')}  
        Customer: {row.get('customer_name','')}  
        Mobile: {row.get('customer_mobile','')}  
        Vehicle: {row.get('vehicle_model','')} ({row.get('vehicle_number','')})  
        Pickup: {row.get('pickup_location','')}  
        Days: {row.get('booking_days','')}  
        Issue: {row.get('issue','')}  
        Priority: {row.get('priority','')}  
        Status: {row.get('status','')}  
        Added By: {row.get('added_by','')}  
        Resolved By: {row.get('resolved_by','')}  
        Created: {row.get('created_at','')}  
        Resolved: {row.get('resolved_at','')}  
        """

    if many.empty:
        st.info("No breakdowns found for selected filters.")
    else:
        # Show all cards
        for _, r in many.iterrows():
            st.code(card(r), language="markdown")

        # Prepare PDF download
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        def make_pdf(data):
            from io import BytesIO
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            width, height = A4
            y = height - 50
            for _, r in data.iterrows():
                lines = card(r).splitlines()
                for line in lines:
                    c.drawString(50, y, line)
                    y -= 15
                    if y < 50:
                        c.showPage()
                        y = height - 50
                y -= 20
            c.save()
            buffer.seek(0)
            return buffer

        pdf_file = make_pdf(many)
        st.download_button(
            "📥 Download PDF",
            data=pdf_file,
            file_name="breakdown_cards.pdf",
            mime="application/pdf"
        )


st.markdown("---")
st.caption("© Rentelo | Built with Streamlit + Google Sheets")

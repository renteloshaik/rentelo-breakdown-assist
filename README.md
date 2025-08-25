# Rentelo Breakdown Assist (Streamlit + Google Sheets)

A professional Streamlit web app to log and track vehicle breakdowns (Scooty/Car) and store all data in **Google Sheets**.

## Features
- Add breakdown with: Booking ID, Customer Mobile, Pickup Location, Booking Days, Issue, Vehicle Number, Vehicle Model, Vehicle Type, Customer Location (Google Maps URL), Latitude/Longitude, Priority, Follow-up By, Added By
- Status workflow: **Open → In Progress → Resolved/Cancelled**
- When status becomes **Resolved**, the app captures **Resolved By** and **Resolved At** (timestamp IST)
- View and update records (status, priority, follow-up)
- Filters by vehicle type, status, priority, follow-up, and **date range**
- Export filtered data as **CSV**
- Generate a **PDF** with printable breakdown cards (one per record)
- Location preview map if latitude/longitude or extractable from Google Maps URL

## Google Sheets Setup
1. Create a Google Sheet (blank). Copy the **Sheet ID** from the URL (the long string between `/d/` and `/edit`).
2. Create a **Service Account** in Google Cloud, download the JSON key.
3. Share your Google Sheet with the service account's **client_email** (Editor).
4. In Streamlit (locally or cloud), add your service account JSON and the Sheet ID to **secrets** (see below).

## Streamlit Secrets (Toml)
In Streamlit Cloud -> App -> Settings -> **Secrets**, paste something like this (replace with your values):

```
# sample_secrets.toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "123456789012345678901"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"

[gsheet]
sheet_id = "your-google-sheet-id"
```

> Also share your Google Sheet with the **client_email** above.

## Local Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud
- Push these files to GitHub (app.py, requirements.txt, README.md)
- Create a new app on Streamlit Cloud pointing to your repo
- Add the **secrets** shown above
- Deploy

## Columns stored in Google Sheet
```
id, created_at, last_updated, booking_id, customer_mobile, pickup_location,
booking_days, issue, vehicle_number, vehicle_model, vehicle_type,
customer_location_url, latitude, longitude, priority, status, followup_by,
added_by, resolved_by, resolved_at
```
- `created_at`, `last_updated`, `resolved_at` in IST, ISO-like format.
- `id` auto-generated like `BD-2508251035-AB`

## Notes
- The app will auto-create a worksheet named **breakdowns** with the above columns.
- If you paste a Google Maps URL, the app tries to extract latitude/longitude automatically.
- "Resolved By" auto-fills from your **Your Name** in the sidebar when status set to **Resolved**.
- Concurrency: Google Sheets is last-writer-wins; avoid simultaneous edits to the same row.

---

© Rentelo — Built with ❤️ using Streamlit

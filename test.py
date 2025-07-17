import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from httplib2 import Http

# Setup Google credentials and APIs
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
drive_service = build("drive", "v3", http=creds.authorize(Http()))

# Find or create folder
folder_name = "Leverage Trade Signals"
query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
results = drive_service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
folders = results.get("files", [])
if folders:
    folder_id = folders[0]["id"]
    print(f"📁 Found folder: {folder_name} (ID: {folder_id})")
else:
    folder_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
    folder_id = folder.get("id")
    print(f"📁 Created folder: {folder_name} (ID: {folder_id})")

print("📄 Creating new Google Sheet: 'Signal Log'")
spreadsheet = client.create("Signal Log")
file_id = spreadsheet.id
drive_service.files().update(
    fileId=file_id,
    addParents=folder_id,
    fields="id, parents"
).execute()
sheet = spreadsheet.sheet1
sheet.append_row(["Test Header 1", "Test Header 2"])
sheet.append_row(["Row 1 Col A", "Row 1 Col B"])
print("✅ Sheet created and row written.")

# Share sheet with your email
user_email = "kenoshaguthrie@gmail.com"
drive_service.permissions().create(
    fileId=file_id,
    body={"type": "user", "role": "writer", "emailAddress": user_email},
    fields="id"
).execute()
print(f"🔐 Shared sheet with {user_email}")

# Final link
print(f"🔗 View it at: https://docs.google.com/spreadsheets/d/{file_id}")
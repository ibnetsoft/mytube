
import os
from supabase import create_client

def get_first_user():
    url = "https://giorysjpgxzdypbmxwmx.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdpb3J5c2pwZ3h6ZHlwYm14d214Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTg0MTc3OSwiZXhwIjoyMDg1NDE3Nzc5fQ.bVpsP4y3NS1yXFpe0YZjKWCz_zHYOiXsEmm_GL3mXHw"
    
    supabase = create_client(url, key)
    # Note: Using auth.admin requires service_role key
    users = supabase.auth.admin.list_users()
    if users:
        for user in users:
            print(f"ID: {user.id}, Email: {user.email}")
    else:
        print("No users found")

if __name__ == "__main__":
    try:
        get_first_user()
    except Exception as e:
        print(f"Error: {e}")

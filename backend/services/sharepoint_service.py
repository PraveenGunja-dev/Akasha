import os
import msal
import requests
from dotenv import load_dotenv

load_dotenv()

from datetime import datetime

class SharePointService:
    def __init__(self):
        self.tenant_id = os.getenv("SHAREPOINT_TENANT_ID")
        self.client_id = os.getenv("SHAREPOINT_CLIENT_ID")
        self.client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
        self.site_url = os.getenv("SHAREPOINT_SITE_URL")
        
        # Determine today's date in DD.MM.YYYY format
        today_str = datetime.now().strftime("%d.%m.%Y")
        
        # The base target folder from env, dynamically appending the date
        base_folder = os.getenv("SHAREPOINT_BASE_FOLDER", "/sites/AGEL-Automation/Shared Documents/Bots/Akasha PlatForm")
        self.target_folder = f"{base_folder}/{today_str}"
        
        # Microsoft Graph API Base URL
        self.graph_url = 'https://graph.microsoft.com/v1.0'
        
        # Site ID is typically needed for Graph API calls; we will resolve it dynamically or assume the user will configure it
        # For simplicity, if we have the site hostname and path, we can address it via Graph API:
        # e.g. https://graph.microsoft.com/v1.0/sites/adaniltd.sharepoint.com:/sites/AGEL-Automation
        self.hostname = "adaniltd.sharepoint.com"
        self.site_path = "/sites/AGEL-Automation"

    def _get_access_token(self):
        """Authenticates with Microsoft Azure AD using Client Credentials flow."""
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret
        )
        
        # We need the .default scope for Microsoft Graph
        scopes = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_for_client(scopes=scopes)
        
        if "access_token" in result:
            return result["access_token"]
        else:
            raise Exception(f"Failed to acquire token: {result.get('error_description')}")

    def get_site_id(self, token):
        """Fetches the Graph API Site ID using the hostname and site path."""
        url = f"{self.graph_url}/sites/{self.hostname}:{self.site_path}"
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("id")

    def list_files_in_target_folder(self):
        """Lists all files in the target folder on SharePoint. Automatically finds the latest date folder."""
        try:
            token = self._get_access_token()
            site_id = self.get_site_id(token)
            
            # First, list the base folder to find the latest date folder
            base_relative_path = os.getenv("SHAREPOINT_BASE_FOLDER", "/sites/AGEL-Automation/Shared Documents/Bots/Akasha PlatForm").replace(f"{self.site_path}/Shared Documents", "").strip("/")
            base_url = f"{self.graph_url}/sites/{site_id}/drive/root:/{base_relative_path}:/children"
            
            headers = {"Authorization": f"Bearer {token}"}
            base_resp = requests.get(base_url, headers=headers)
            base_resp.raise_for_status()
            
            folders = [f for f in base_resp.json().get("value", []) if f.get("folder")]
            if not folders:
                print("No date folders found in base folder.")
                return []
                
            # Sort folders by name (assuming format DD.MM.YYYY, but we should parse it to be safe, or just take the one matching today/yesterday)
            # A simple approach: sort by modified date or parse DD.MM.YYYY
            def parse_date(name):
                try:
                    return datetime.strptime(name, "%d.%m.%Y")
                except:
                    return datetime.min
            
            latest_folder = sorted(folders, key=lambda x: parse_date(x["name"]), reverse=True)[0]
            print(f"Using latest SharePoint folder: {latest_folder['name']}")
            
            self.target_folder = f"{os.getenv('SHAREPOINT_BASE_FOLDER', '/sites/AGEL-Automation/Shared Documents/Bots/Akasha PlatForm')}/{latest_folder['name']}"
            relative_path = self.target_folder.replace(f"{self.site_path}/Shared Documents", "").strip("/")
            
            # Construct the Graph API URL for the drive item children
            url = f"{self.graph_url}/sites/{site_id}/drive/root:/{relative_path}:/children"
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            files = response.json().get("value", [])
            return [{"name": f["name"], "id": f["id"], "download_url": f.get("@microsoft.graph.downloadUrl")} for f in files]
            
        except Exception as e:
            print(f"Error fetching files from SharePoint: {e}")
            return []

    def download_file(self, download_url, save_path):
        """Downloads a file from SharePoint using its download URL."""
        response = requests.get(download_url)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return save_path

if __name__ == "__main__":
    # Test the service locally if run directly
    sp_service = SharePointService()
    files = sp_service.list_files_in_target_folder()
    print("Files found in target folder:")
    for f in files:
        print(f["name"])

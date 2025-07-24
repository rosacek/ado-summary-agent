import requests
import logging
from .auth import get_access_token
import base64

logger = logging.getLogger(__name__)

class ADOClient:
    def __init__(self, organization, project, personal_access_token=None):
        self.organization = organization
        self.project = project
        self.personal_access_token = personal_access_token
        self.base_url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/wit/workitems"

    def get_work_items(self, work_item_ids):
        # Determine auth header: PAT (Basic) or Azure CLI (Bearer)
        if self.personal_access_token:
            token = f":{self.personal_access_token}"
            auth_value = f"Basic {base64.b64encode(token.encode()).decode()}"
        else:
            # Use Azure CLI to fetch a bearer token
            bearer = get_access_token()
            auth_value = f"Bearer {bearer}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': auth_value,
        }
        work_items = []
        all_work_item_ids = set(work_item_ids)  # Track all IDs to avoid duplicates
        
        for work_item_id in work_item_ids:
            # Fetch main work item (request all fields)
            response = requests.get(f"{self.base_url}/{work_item_id}?$expand=all&api-version=6.0", headers=headers)
            if response.status_code == 200:
                work_item = response.json()
                # Debug: print all fields received
                logger.debug(f"Work item {work_item_id} fields: {list(work_item.get('fields', {}).keys())}")
                work_items.append(work_item)
                
                # Fetch linked work items
                linked_items = self._get_linked_work_items(work_item_id, headers)
                for linked_item in linked_items:
                    linked_id = linked_item.get('id')
                    if linked_id and linked_id not in all_work_item_ids:
                        all_work_item_ids.add(linked_id)
                        work_items.append(linked_item)
            else:
                logger.error(f"Failed to fetch work item {work_item_id}: {response.status_code} {response.text}")
        return work_items

    def _get_linked_work_items(self, work_item_id, headers):
        """Fetch work items linked to the given work item"""
        linked_items = []
        try:
            # Get work item relations
            relations_url = f"{self.base_url}/{work_item_id}?$expand=relations&api-version=6.0"
            response = requests.get(relations_url, headers=headers)
            
            if response.status_code == 200:
                work_item_data = response.json()
                relations = work_item_data.get('relations', [])
                
                for relation in relations:
                    # Check if this is a work item link (not attachment, etc.)
                    if relation.get('rel') in ['System.LinkTypes.Related', 'System.LinkTypes.Hierarchy-Forward', 
                                               'System.LinkTypes.Hierarchy-Reverse', 'System.LinkTypes.Dependency-Forward',
                                               'System.LinkTypes.Dependency-Reverse']:
                        url = relation.get('url', '')
                        if '/workItems/' in url:
                            # Extract work item ID from URL
                            linked_id = int(url.split('/workItems/')[-1])
                            
                            # Fetch the linked work item details
                            linked_response = requests.get(f"{self.base_url}/{linked_id}?api-version=6.0", headers=headers)
                            if linked_response.status_code == 200:
                                linked_item = linked_response.json()
                                # Add relationship context
                                linked_item['_relationship'] = relation.get('rel', 'Related')
                                linked_items.append(linked_item)
                            
        except Exception as e:
            logger.warning(f"Failed to fetch linked items for {work_item_id}: {e}")
            
        return linked_items

    def get_work_item_history(self, work_item_id):
        """Fetch the full update history (discussion, comments, state changes) for a work item."""
        if self.personal_access_token:
            token = f":{self.personal_access_token}"
            auth_value = f"Basic {base64.b64encode(token.encode()).decode()}"
        else:
            bearer = get_access_token()
            auth_value = f"Bearer {bearer}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': auth_value,
        }
        updates_url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/wit/workItems/{work_item_id}/updates?api-version=6.0"
        response = requests.get(updates_url, headers=headers)
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            logger.error(f"Failed to fetch history for work item {work_item_id}: {response.status_code} {response.text}")
            return []
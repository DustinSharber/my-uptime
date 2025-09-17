import json
import os
from datetime import datetime
from threading import Lock

class JsonDatabase:
    def __init__(self, data_folder='data'):
        # Ensure the data folder path is absolute
        if not os.path.isabs(data_folder):
            data_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', data_folder)
        
        self.data_folder = data_folder
        self.model_files = {
            'monitor': os.path.join(data_folder, 'monitors.json'),
            'check': os.path.join(data_folder, 'checks.json'),
            'incident': os.path.join(data_folder, 'incidents.json'),
            'notification_channel': os.path.join(data_folder, 'notification_channels.json'),
            'history': os.path.join(data_folder, 'history.json'),
            'maintenance': os.path.join(data_folder, 'maintenances.json'),
            'status_page': os.path.join(data_folder, 'status_pages.json'),
            'agent_metric': os.path.join(data_folder, 'agent_metrics.json'),
            'agent_log': os.path.join(data_folder, 'agent_logs.json'),
            'tag': os.path.join(data_folder, 'tags.json'),
            'monitor_tag': os.path.join(data_folder, 'monitor_tags.json'),
            'command': os.path.join(data_folder, 'commands.json'),
            'pending_command': os.path.join(data_folder, 'pending_commands.json'),
            'user': os.path.join(data_folder, 'users.json'),
            'backup_config': os.path.join(data_folder, 'backup_configs.json'),
        }
        self._locks = {file_path: Lock() for file_path in self.model_files.values()}
        self.ensure_data_files()

    def ensure_data_files(self):
        os.makedirs(self.data_folder, exist_ok=True)
        for file_path in self.model_files.values():
            if not os.path.exists(file_path):
                with self._locks[file_path]:
                    if not os.path.exists(file_path):
                        with open(file_path, 'w') as f:
                            json.dump([], f)

    def read_data(self, file_path):
        with self._locks[file_path]:
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []

    def write_data(self, file_path, data):
        with self._locks[file_path]:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)

    def get_all(self, model_name):
        file_path = self.model_files.get(model_name)
        if not file_path:
            raise ValueError(f"Unknown model: {model_name}")
        return self.read_data(file_path)

    def get_by_id(self, model_name, item_id):
        items = self.get_all(model_name)
        return next((item for item in items if item['id'] == item_id), None)

    def add(self, model_name, item_data):
        file_path = self.model_files.get(model_name)
        if not file_path:
            raise ValueError(f"Unknown model: {model_name}")
        items = self.read_data(file_path)
        item_data['id'] = self.get_next_id(items)
        item_data['created_at'] = datetime.utcnow().isoformat()
        item_data['updated_at'] = datetime.utcnow().isoformat()
        items.append(item_data)
        self.write_data(file_path, items)
        return item_data

    def update(self, model_name, item_id, update_data):
        file_path = self.model_files.get(model_name)
        if not file_path:
            raise ValueError(f"Unknown model: {model_name}")
        items = self.read_data(file_path)
        for item in items:
            if item['id'] == item_id:
                item.update(update_data)
                item['updated_at'] = datetime.utcnow().isoformat()
                break
        self.write_data(file_path, items)

    def delete(self, model_name, item_id):
        file_path = self.model_files.get(model_name)
        if not file_path:
            raise ValueError(f"Unknown model: {model_name}")
        items = self.read_data(file_path)
        items = [item for item in items if item['id'] != item_id]
        self.write_data(file_path, items)

    def get_next_id(self, items):
        return max([item['id'] for item in items]) + 1 if items else 1

db = JsonDatabase()

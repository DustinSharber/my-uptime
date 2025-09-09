import json
import os
from datetime import datetime
from threading import Lock

class JsonDatabase:
    def __init__(self, data_folder='data'):
        self.data_folder = data_folder
        self.monitors_file = os.path.join(data_folder, 'monitors.json')
        self.checks_file = os.path.join(data_folder, 'checks.json')
        self.incidents_file = os.path.join(data_folder, 'incidents.json')
        self.notification_channels_file = os.path.join(data_folder, 'notification_channels.json')
        self.history_file = os.path.join(data_folder, 'history.json')
        self.maintenances_file = os.path.join(data_folder, 'maintenances.json')
        self.status_pages_file = os.path.join(data_folder, 'status_pages.json')
        self.agent_metrics_file = os.path.join(data_folder, 'agent_metrics.json')
        self._locks = {
            self.monitors_file: Lock(),
            self.checks_file: Lock(),
            self.incidents_file: Lock(),
            self.notification_channels_file: Lock(),
            self.history_file: Lock(),
            self.maintenances_file: Lock(),
            self.status_pages_file: Lock(),
            self.agent_metrics_file: Lock(),
        }
        self.ensure_data_files()

    def ensure_data_files(self):
        os.makedirs(self.data_folder, exist_ok=True)
        for file_path in [self.monitors_file, self.checks_file, self.incidents_file, self.notification_channels_file, self.history_file, self.maintenances_file, self.status_pages_file, self.agent_metrics_file]:
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
        if model_name == 'history':
            file_path = self.history_file
        else:
            file_path = getattr(self, f"{model_name}s_file")
        return self.read_data(file_path)

    def get_by_id(self, model_name, item_id):
        items = self.get_all(model_name)
        return next((item for item in items if item['id'] == item_id), None)

    def add(self, model_name, item_data):
        file_path = getattr(self, f"{model_name}s_file")
        items = self.read_data(file_path)
        item_data['id'] = self.get_next_id(items)
        item_data['created_at'] = datetime.utcnow().isoformat()
        item_data['updated_at'] = datetime.utcnow().isoformat()
        items.append(item_data)
        self.write_data(file_path, items)
        return item_data

    def update(self, model_name, item_id, update_data):
        file_path = getattr(self, f"{model_name}s_file")
        items = self.read_data(file_path)
        for item in items:
            if item['id'] == item_id:
                item.update(update_data)
                item['updated_at'] = datetime.utcnow().isoformat()
                break
        self.write_data(file_path, items)

    def delete(self, model_name, item_id):
        file_path = getattr(self, f"{model_name}s_file")
        items = self.read_data(file_path)
        items = [item for item in items if item['id'] != item_id]
        self.write_data(file_path, items)

    def get_next_id(self, items):
        return max([item['id'] for item in items]) + 1 if items else 1

db = JsonDatabase()

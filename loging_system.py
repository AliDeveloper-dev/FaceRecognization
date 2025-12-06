import json
from datetime import datetime

class SecurityLogger:
    def __init__(self):
        self.log_file = 'security_logs.json'
        
    def log_event(self, event_type, details):
        """Log security events"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'details': details
        }
        
        try:
            with open(self.log_file, 'r') as f:
                logs = json.load(f)
        except FileNotFoundError:
            logs = []
        
        logs.append(log_entry)
        
        with open(self.log_file, 'w') as f:
            json.dump(logs, f, indent=2)
        
        # Print to console
        print(f"[{log_entry['timestamp']}] {event_type}: {details}")
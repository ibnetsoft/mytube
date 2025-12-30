from proglog import ProgressBarLogger
import time

# Global store for render progress: {project_id: percentage} (0-100)
# Also store state: 'rendering', 'completed', 'failed'
RENDER_PROGRESS = {}

class RenderLogger(ProgressBarLogger):
    def __init__(self, project_id):
        super().__init__()
        self.project_id = project_id
        self.last_update = 0
        RENDER_PROGRESS[project_id] = {
            "status": "starting",
            "progress": 0
        }

    def callback(self, **changes):
        # changes format: {'bars': {'t': {'index': 50, 'total': 100, ...}}}
        if 'bars' in changes:
            bars = changes['bars']
            if 't' in bars: # 't' is the time iterator in moviepy
                t_bar = bars['t']
                index = t_bar.get('index', 0)
                total = t_bar.get('total', 1) # Avoid division by zero
                
                if total > 0:
                    percentage = int((index / total) * 100)
                    # Update global store (throttle updates slightly if needed, but simple is fine)
                    RENDER_PROGRESS[self.project_id] = {
                        "status": "rendering",
                        "progress": percentage
                    }

    def bars_callback(self, bar, attr, value, old_value=None):
        # Some versions of proglog use this
        pass

def get_render_progress(project_id):
    return RENDER_PROGRESS.get(project_id, {"status": "unknown", "progress": 0})

def set_render_status(project_id, status, progress=0):
    RENDER_PROGRESS[project_id] = {
        "status": status,
        "progress": progress
    }

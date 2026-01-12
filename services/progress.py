from proglog import ProgressBarLogger
import time

# Global store for render progress: {project_id: percentage} (0-100)
# Also store state: 'rendering', 'completed', 'failed'
RENDER_PROGRESS = {}

class RenderLogger(ProgressBarLogger):
    def __init__(self, project_id, start_pct=0, end_pct=100):
        super().__init__()
        self.project_id = project_id
        self.start_pct = start_pct
        self.end_pct = end_pct
        self.last_update = 0
        
        # Initialize or update existing progress to the start_pct
        RENDER_PROGRESS[project_id] = {
            "status": "rendering",
            "progress": start_pct
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
                    # Calculate percentage within the given range [start_pct, end_pct]
                    local_percentage = index / total
                    range_size = self.end_pct - self.start_pct
                    global_percentage = int(self.start_pct + (local_percentage * range_size))
                    
                    # Update global store
                    RENDER_PROGRESS[self.project_id] = {
                        "status": "rendering",
                        "progress": global_percentage
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

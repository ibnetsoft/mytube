"""
[AIR-0227E-P2] AIR Worker's own version marker - deliberately separate from
the root version.py (APP_VERSION), which belongs to AIR Studio Desktop's own
install/update channel. AIR Worker ships and updates on an independent
cadence (it's a different executable, targeting rendering PCs, not end-user
desktops) and per this Task's explicit instruction must not be mixed with
AIR Studio Desktop's channel - see docs/AIR_WORKER_UPDATE_STRATEGY.md §P2-15.
packaging/windows/AIRWorker.iss reads this via the AIRWORKER_VERSION env var
(set by a build script), the same pattern AIRStudio.iss uses for AIR_VERSION
from the root version.py - two parallel, independent single sources of truth.
"""
WORKER_VERSION = "0.1.0"

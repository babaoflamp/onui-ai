import os
import tempfile

import uvicorn

from backend.config import load_settings
from backend.core.app import create_app
from backend.database import initialize_database

# Initialize Application
app = create_app()

# Setup OS-level Environment Variables based on settings
settings = load_settings()
os.environ["TMPDIR"] = str(settings.app_tmp_dir)
os.environ["TEMP"] = str(settings.app_tmp_dir)
os.environ["TMP"] = str(settings.app_tmp_dir)
tempfile.tempdir = str(settings.app_tmp_dir)

# Initialize Database on startup
initialize_database(str(settings.db_path))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9002, reload=True)

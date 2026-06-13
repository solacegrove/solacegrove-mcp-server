import sys
import os

# Add the parent directory to sys.path to allow importing 'server'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.server import main

if __name__ == "__main__":
    sys.exit(main())

import sys
import os

# Add the directory containing 'server' to sys.path
# This ensures that 'import server.server' works regardless of where python is started
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from server.server import main
except ImportError:
    # Fallback for when 'server' is already in path but not as a package
    import server as server_mod
    main = server_mod.main

if __name__ == "__main__":
    sys.exit(main())

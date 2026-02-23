"""
Run from inside the healthcare_agent/ folder:
    python start.py
"""
import sys
import os

# Add the parent directory so 'healthcare_agent' is importable as a package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healthcare_agent.main import main

if __name__ == "__main__":
    main()

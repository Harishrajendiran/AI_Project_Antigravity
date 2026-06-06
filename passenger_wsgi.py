import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask application object
# Passenger expects the variable name to be 'application'
from app import app as application

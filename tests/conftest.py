"""Tests run headless, whatever backend the calling notebook set."""
import os

os.environ["MPLBACKEND"] = "Agg"

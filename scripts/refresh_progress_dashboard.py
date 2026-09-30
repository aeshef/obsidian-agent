"""Rebuild interactive task data on demand."""
import argparse
from pathlib import Path
from unified_bot.integrations.dashboard_datasets import refresh_progress
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--vault', type=Path, required=True)
    refresh_progress(parser.parse_args().vault)

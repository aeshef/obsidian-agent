"""python -m planning_bot.tools.vault_maintenance"""
import sys
from planning_bot.tools.vault_maintenance import add_ids_to_tasks, run_all

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--ids-only', action='store_true')
    a = p.parse_args()
    sys.exit(0 if (add_ids_to_tasks() if a.ids_only else run_all()) else 1)

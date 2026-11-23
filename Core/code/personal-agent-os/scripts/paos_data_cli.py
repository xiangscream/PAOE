"""Explicit Data migration CLI slice; the main paos.py is integrated separately."""
import argparse
import json
import sys

from paos_data_migration import plan, execute, rollback
from paos_installation import resolve_installation_path, InstallationProblem
from paos_registry import RegistryProblem


def add_data_parsers(sub):
    data = sub.add_parser('data', help='Installation machine stores').add_subparsers(dest='data_command', required=True)
    actions = data.add_parser('migrate', help='Explicit plan, execute or rollback').add_subparsers(dest='migration_command', required=True)
    actions.add_parser('plan', help='Read sources without writes')
    actions.add_parser('execute', help='Migrate with a durable recovery receipt').add_argument('--before-state', required=True)
    actions.add_parser('rollback', help='Restore old-code routes and preserve post-cutover facts').add_argument('--before-state', required=True)


def execute_data(args, installation):
    if args.migration_command == 'plan':
        return plan(installation)
    if args.migration_command == 'execute':
        return execute(installation, args.before_state)
    return rollback(args.before_state, installation_path=installation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation-file', required=True)
    add_data_parsers(parser.add_subparsers(dest='command', required=True))
    args = parser.parse_args()
    try:
        result = execute_data(args, resolve_installation_path(args.installation_file))
    except (OSError, ValueError, InstallationProblem, RegistryProblem) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())

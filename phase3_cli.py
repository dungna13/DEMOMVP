"""
phase3_cli.py — Batch CLI cho Phase 3 Knowledge Wiki
Usage:
  python phase3_cli.py compile [--limit N] [--all]
  python phase3_cli.py lint
  python phase3_cli.py status
"""
import argparse
import logging
import sys
import io

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def cmd_compile(args):
    from src.services.wiki_compiler import compile_all_wiki, get_wiki_status
    skip = not args.all
    logger.info(f"Compiling wiki (limit={args.limit}, skip_existing={skip})...")
    count = compile_all_wiki(limit=args.limit, skip_existing=skip)
    logger.info(f"Done: {count} documents compiled.")
    status = get_wiki_status()
    print(f"\n[OK] Status: {status['wiki_compiled']}/{status['total_documents']} compiled | {status['wiki_pages']} wiki pages | vault: {status['vault_dir']}")


def cmd_lint(args):
    from src.services.wiki_compiler import lint_wiki
    logger.info("Running wiki lint checks...")
    issues = lint_wiki()
    if not issues:
        print("[OK] No issues found.")
    else:
        print(f"[WARN] Found issues in {len(issues)} page(s):")
        for page in issues:
            print(f"\n  [{page['page_slug']}] {page['title'][:60]}")
            for issue in page["issues"]:
                print(f"    - {issue['type']}: {issue.get('link', issue.get('doc_id', ''))}")


def cmd_status(args):
    from src.services.wiki_compiler import get_wiki_status
    s = get_wiki_status()
    print(f"""
[Phase 3] Knowledge Wiki Status
================================
 Documents total   : {s['total_documents']}
 Wiki compiled     : {s['wiki_compiled']}
 Wiki pages in DB  : {s['wiki_pages']}
 Reviewed          : {s['reviewed']}
 Pending review    : {s['pending_review']}
 Lint issues       : {s['lint_issues']}
 Vault directory   : {s['vault_dir']}
 JSON data dir     : {s['wiki_data_dir']}
""")


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Knowledge Wiki CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_compile = sub.add_parser("compile", help="Compile wiki pages from documents")
    p_compile.add_argument("--limit", type=int, default=None, help="Max documents to process")
    p_compile.add_argument("--all", action="store_true", help="Re-compile all (including existing)")

    sub.add_parser("lint", help="Run wiki lint checks")
    sub.add_parser("status", help="Show Phase 3 status")

    args = parser.parse_args()

    if args.cmd == "compile":
        cmd_compile(args)
    elif args.cmd == "lint":
        cmd_lint(args)
    elif args.cmd == "status":
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

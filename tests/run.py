"""Tiny test runner. python tests/run.py [module | module.test ...]  (ponytail: no pytest, asserts only)"""
import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from tests.paths import SkipTest  # noqa: E402


def main(args):
    targets = args or sorted(p.stem for p in (ROOT / 'tests').glob('test_*.py'))
    failed = 0
    for target in targets:
        module_name, _, only = target.partition('.')
        mod = importlib.import_module(f'tests.{module_name}')
        for name in sorted(n for n in dir(mod) if n.startswith('test_') and (not only or n == only)):
            try:
                getattr(mod, name)()
                print(f'PASS {module_name}.{name}')
            except SkipTest as e:
                print(f'SKIP {module_name}.{name}: {e}')
            except Exception:
                failed += 1
                print(f'FAIL {module_name}.{name}')
                traceback.print_exc()
    print('OK' if not failed else f'FAILED: {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

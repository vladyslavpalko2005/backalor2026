"""Package server sources only: never scans, local databases, .env or sessions."""
from pathlib import Path
import argparse
import zipfile
ROOT=Path(__file__).resolve().parent.parent


def package(target):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    fixed=['Dockerfile','.dockerignore','render.yaml','requirements-backend.txt','.env.cloud.example',
           'CLOUD.md','deploy/docker-entrypoint.sh']
    sources=[ROOT/name for name in fixed]+sorted((ROOT/'backend').glob('*.py'))
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for source in sources:archive.write(source,source.relative_to(ROOT))
    return len(sources)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'dist/backalor-cloud-source.zip')
    args=parser.parse_args();print('Server files:',package(args.output));print(args.output)


if __name__=='__main__':main()

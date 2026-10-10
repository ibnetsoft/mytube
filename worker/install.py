"""Install a source worker in its own Python environment; preserve connection settings."""
import argparse, subprocess, sys, venv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--role',choices=['script','local'],required=True);args=parser.parse_args()
    if sys.version_info<(3,11):raise SystemExit('Python 3.11 or later is required')
    target=ROOT/('.venv-'+args.role)
    venv.EnvBuilder(with_pip=True).create(target)
    python=target/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    requirements=ROOT/('worker/requirements-script.txt' if args.role=='script' else 'requirements.txt')
    subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True)
    sample=ROOT/'worker/connection.env.example';settings=ROOT/'worker/connection.env'
    if not settings.exists():settings.write_bytes(sample.read_bytes())
    print('Installed. Configure worker/connection.env on this computer; no credentials are included.')
    print(str(python)+' -m worker.launch --role '+args.role+' --env-file worker/connection.env')
if __name__=='__main__':main()

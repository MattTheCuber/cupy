#!/usr/bin/env python

"""
Generates a wheel metadata.

This tool is NOT intended for end-user use.
"""

# This script will also be used as a standalone script when building wheels.
# Keep the script runnable without CuPy dependency.

import argparse
import json
import os.path
import platform
import subprocess
import sys


def _get_records(library: str, cuda: str):
    command = [
        sys.executable,
        'install_library.py',
        '--library', library,
        '--cuda', cuda,
        '--action', 'dump',
    ]
    return json.loads(
        subprocess.check_output(command, cwd=os.path.dirname(__file__)))


def _generate_wheel_metadata(cuda_version, target_system, libraries):
    wheel_metadata = {
        'cuda': cuda_version,
        'packaging': 'pip',
    }
    for library in libraries:
        for record in _get_records(library, cuda_version):
            if record['cuda'] == cuda_version:
                metadata = {
                    'version': record[library],
                    'filenames': record['assets'][target_system]['filenames'],
                }
                break
        else:
            raise RuntimeError(
                'Specified library/CUDA combination not supported')
        wheel_metadata[library] = metadata

    return wheel_metadata


def main(args):
    parser = argparse.ArgumentParser()

    parser.add_argument('--cuda', type=str, required=True,
                        help='CUDA version')
    parser.add_argument('--target', type=str,
                        help='Target system (default: platform.system())')
    parser.add_argument('--library',
                        choices=['cudnn', 'cutensor', 'nccl'],
                        action='append',
                        required=True)
    params = parser.parse_args(args)

    print(json.dumps(
        _generate_wheel_metadata(
            params.cuda,
            params.target or platform.system(),
            params.library,
        ), indent=4
    ))


if __name__ == '__main__':
    main(sys.argv[1:])

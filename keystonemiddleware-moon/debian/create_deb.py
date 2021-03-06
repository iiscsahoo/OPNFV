#!/usr/bin/env python3.5

import os
import sys
import subprocess
import glob
import argparse


parser = argparse.ArgumentParser()
parser.add_argument('--src', help='Do not clone Moon repository, use SRC as source directory', dest="src")
args = parser.parse_args()


TMP_DIR = "/tmp/debian-moon"
MOON_DIR = os.path.join(TMP_DIR, "moon")
INIT_dir = os.path.split(os.path.abspath(sys.argv[0]))[0]

print("init dir: {}".format(INIT_dir))

_run = subprocess.run(["mkdir", "-p", TMP_DIR])
if _run.returncode != 0:
    exit("\033[31mCannot create tmp dir\033[m")

os.chdir(TMP_DIR)

_run = subprocess.run(["sudo", "apt-get", "install", "-y", "git"])
if _run.returncode != 0:
    exit("\033[31mCannot install Git\033[m")

# print("\033[32mCloning Debian version\033[m")
# _run = subprocess.run(["git", "clone", "https://anonscm.debian.org/git/openstack/python-keystonemiddleware.git"])
# if _run.returncode != 0:
#     os.chdir(os.path.join(TMP_DIR, "python-keystonemiddleware"))
#     _run = subprocess.run(["git", "pull"])
#     if _run.returncode != 0:
#         print("\033[31mCannot clone ou pull debian version\033[m")

os.chdir(TMP_DIR)

if args.src:
    print("\033[32mUsing {} as source directory\033[m".format(args.src))
    MOON_DIR = args.src
else:
    print("\033[32mCloning Moon project\033[m")
    _run = subprocess.run(["git", "clone", "https://git.opnfv.org/moon"])
    if _run.returncode != 0:
        os.chdir(os.path.join(TMP_DIR, "moon"))
        _run = subprocess.run(["git", "pull"])
        if _run.returncode != 0:
            print("\033[31mCannot clone Moon project\033[m")

os.chdir(TMP_DIR)

# src_path = os.path.join(TMP_DIR, "python-keystonemiddleware", "debian")
# dst_path = os.path.join(TMP_DIR, "moon", "keystonemiddleware-moon")
# print("\033[32mCopying from {} to {}\033[m".format(src_path, dst_path))
# _run = subprocess.run(["cp",
#                        "-rv",
#                        src_path,
#                        dst_path])

print("\033[32mBuilding Moon project\033[m")
os.chdir(os.path.join(MOON_DIR, "keystonemiddleware-moon"))

mandatory_deb_pkg = """dh-apparmor
dh-systemd
openstack-pkg-tools
python-all python-pbr
python-sphinx
python-bashate
python-keystonemiddleware
python-ldap
python-ldappool
python-memcache
python-migrate
python-mock
python-msgpack
python-oslo.cache
python-oslo.concurrency
python-oslo.config
python-oslo.context
python-oslo.db
python-oslo.i18n
python-oslo.log
python-oslo.messaging
python-oslo.policy
python-oslo.serialization
python-oslo.service
python-oslo.utils
python-oslosphinx
python-oslotest
python-os-testr
python-passlib
python-paste
python-pastedeploy
python-pycadf
python-pymongo
python-pysaml2
python-pysqlite2
python-routes
python-sqlalchemy
python-stevedore
python-testscenarios
python-testtools
python-unittest2
python-webob
python-webtest
subunit
testrepository
python-coverage
python-dogpile.cache
python-eventlet
python-hacking
python-oslo.cache
python-oslo.concurrency
python-oslo.config
python-oslo.db
python-oslo.log
python-oslo.messaging
python-oslo.middleware
python-tempest-lib
python-oauthlib
python-pam
python3-all
python3-setuptools
python-bandit
python-requests-mock
python-testresources
python3-bandit
python3-crypto
python3-keystoneauth1
python3-keystoneclient
python3-memcache
python3-mock
python3-oslo.config
python3-oslo.context
python3-oslo.i18n
python3-oslo.messaging
python3-oslo.serialization
python3-oslo.utils
python3-oslotest
python3-positional
python3-pycadf
python3-requests-mock
python3-stevedore
python3-testresources
python3-webob
"""

_command = ["sudo", "apt-get", "install", "-y"]
_command.extend(mandatory_deb_pkg.split())
_run = subprocess.run(_command)

print("\033[32mremove a Debian patch as it inserts a bug in Moon\033[m")
series_filename = os.path.join(MOON_DIR, "keystonemiddleware-moon",
                               "debian", "patches", "series")
series_lines = open(series_filename).readlines()

output = open(series_filename, "w")
for line in series_lines:
    if "re-add-missing-auth-options.patch" not in line:
        output.write(line)
        output.write("\n")
output.close()
os.remove(os.path.join(MOON_DIR, "keystonemiddleware-moon",
                       "debian", "patches", "re-add-missing-auth-options.patch"))

os.putenv("DEB_BUILD_OPTIONS", "nocheck")

changelog = open(os.path.join(MOON_DIR, "keystonemiddleware-moon", "debian", "changelog"), "rt")
changelog_str = changelog.read()
# print(changelog_str.splitlines()[0])
current_version = changelog_str.splitlines()[0].split("(")[1].split(")")[0]
changelog.close()
changelog = open(os.path.join(MOON_DIR, "keystonemiddleware-moon", "debian", "changelog"), "wt")
changelog.write("""python-keystonemiddleware ({version}) UNRELEASED; urgency=medium

  * integration of the Moon platform.

 -- Thomas Duval <thomas.duval@orange.com>  {date}

""".format(
    version=current_version+"-moon",
    date=subprocess.Popen(["date"], stdin=None, stdout=subprocess.PIPE).communicate()[0].decode("utf-8").strip()))
changelog.write(changelog_str)
changelog.close()

_run = subprocess.run(["dpkg-buildpackage", "-b", "-us"])

print("\033[32mResults:\033[m")
subprocess.run(["mkdir", "-p", "/tmp/deb"])

files = glob.glob(os.path.join(MOON_DIR, "*.deb"))
for _file in files:
    subprocess.run(["mv", "-v", _file, "/tmp/deb/"])

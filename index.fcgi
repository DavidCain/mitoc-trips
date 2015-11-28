#!/usr/bin/env python

"""
FastCGI script for deployment on Scripts.

Should be placed in `web_scripts` of the appropriate locker, in a directory
whose name the app should be served under.

For example, to serve at the URL http://mitoc/scripts.mit.edu/ws/, this file
should reside in `/mit/mitoc/web_scripts/ws/.`
"""
import os
import site
import sys
import time
import threading


app_name = 'ws'
base_dir = '/mit/mitoc/Scripts/django/ws'

# Add the site-packages of the chosen virtualenv to work with
virtualenv_root = '/mit/mitoc/Scripts/ws_virtualenv/'
site.addsitedir(os.path.join(virtualenv_root, 'local/lib/python2.7/site-packages'))

# Add the app's directory to the PYTHONPATH
sys.path.insert(0, os.path.join(base_dir, app_name))
sys.path.insert(0, base_dir)

#to set enviroment settings for Django apps
os.chdir(base_dir)
os.environ['DJANGO_SETTINGS_MODULE'] = app_name + '.settings'

# Activate virtual env to gain access to Django 1.8 & other project dependencies
activate_env = os.path.expanduser(os.path.join(virtualenv_root, 'bin/activate_this.py'))
execfile(activate_env, dict(__file__=activate_env))

# Imports must be done _after_ activating virtual environment
import django
import django.utils.autoreload

django.setup()


def reloader_thread():
    while True:
        if django.utils.autoreload.code_changed():
            os._exit(3)
        time.sleep(1)

t = threading.Thread(target=reloader_thread)
t.daemon = True
t.start()

from django.core.servers.fastcgi import runfastcgi
runfastcgi(method="threaded", daemonize="false")

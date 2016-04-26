# About
This is a Django-based trip management system for the [MIT Outing Club][mitoc].

MITOC's volunteer leaders craft trips to take participants climbing, hiking,
biking, skiing, mountaineering, paddling, surfing. All trips are open to MITOC
members - a community of thousands.

# Deployment
## Deploying locally

This project is designed to be rapidly deployed on a local system for testing.
For instance, using Django's console-based email backend removes the need for
an SMTP server.

The default settings (`conf/local_settings.py`) contain everything you need to
get up and running on your own machine.


### Database configuration

The default local settings are for a Postgres server, but the system is
database-agnostic. The following SQL servers were used for local deveopment:

- SQLite (Sep 2014 to Oct 2015)
- MySQL (Oct 2016 - Apr 2016)
- Postgres (Apr 2016 - current)

The default `local_settings.py` expects a Postgres database named `ws`. If
using another database backend, modify this file to reflect the chosen backend,
credentials, etc.

After creating the database and necessary roles, run the migrations:

    ./manage.py migrate

### Installation

Create a virtual environment in which to install all dependencies:

    virtualenv venv
    source venv/bin/activate
    pip install -r requirements.txt


### Running the server

    ./manage.py migrate
    WS_DJANGO_LOCAL=1 ./manage.py runserver


The app should now be running at [http://localhost:8000](http://localhost:8000).


  [mitoc]: mitoc.org
  [trips]: trips.mitoc.org

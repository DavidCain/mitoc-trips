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

This project uses Postgres in both development and production, but the system
is database-agnostic. The default `local_settings.py` expects databases named
`ws` and `auth_db`. Modify this file to match your credentials or alternate
backend.

After creating the `ws` and `auth_db` databases, run the migrations:

    ./manage.py migrate

### Installation

Create a virtual environment in which to install all Python dependencies:

    virtualenv venv
    source venv/bin/activate
    pip install -r requirements.txt

Run Bower to download JavaScript libraries.

    npm install bower
    bower install


### Running the server

    ./manage.py migrate
    WS_DJANGO_LOCAL=1 ./manage.py runserver


The app should now be running at [http://localhost:8000](http://localhost:8000).


  [mitoc]: mitoc.org
  [trips]: mitoc-trips.mit.edu

# How to run tests

```bash
poetry install
poetry run ./manage.py test
```

# Common gotchas
## Use `TestCase.multi_db == True` for authentication & geardb tests
Any unit test that interacts with authentication (the `User` model, for example), will
update tables in the `auth_user` database. Any unit test for the gear database will affect
geardb. The default behavior of the `TestCase` class is to only wrap
transactions for the default database, so unless `multi_db` is `True`, changes will leak
across test cases.

Instead of using `django.test.TestCase`, it's recommended to use `ws.tests.TestCase`
(a light wrapper that ensures `multi_db` is always set to `True`).

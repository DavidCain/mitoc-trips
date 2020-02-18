# How to run tests

To execute the whole test suite and collect coverage metrics:

```bash
make test
```

## Optional: Visualize test coverage
```
make test
coverage html  # Then open htmlcov/index.html
```

# Common gotchas
## Put `auth_db` and/or `gear` in databases for authentication & geardb tests
Any unit test that interacts with authentication (the `User` model, for example), will
update tables in the `auth_db` database. Any unit test for the gear database will affect
geardb. The default behavior of the `TestCase` class is to only wrap transactions for
the default database, so unless `databases` are specified, the test runner will fail.

Instead of using `django.test.TestCase`, it's recommended to use `ws.tests.TestCase`
(a light wrapper that ensures all three databases can be queried).

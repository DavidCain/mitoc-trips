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
## Specify `databases` with `geardb` if using gear logic
Any unit test for the gear database will affect geardb. The default behavior of
the `TestCase` class is to only wrap transactions for the default database, so
unless `databases` are specified, the test runner will fail.

Note that we're trying to drop direct MySQL access altogether, so new tests
should not introduce direct dependence on MySQL queries. Instead, just mock
functions as needed.

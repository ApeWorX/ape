# This script proves that we are allowed to have scripts
# with the same name as a built-in site package, e.g. `site.py`.
# This script also shows that the module doesn't load until called.
print("Super secret script output")  # noqa: T001

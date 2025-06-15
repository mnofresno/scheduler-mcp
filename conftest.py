import pytest

# Register the asyncio mark so that async tests (using @pytest.mark.asyncio) do not trigger a warning.
# (See https://docs.pytest.org/en/stable/how-to/mark.html for details.)
pytestmark = [pytest.mark.asyncio] 
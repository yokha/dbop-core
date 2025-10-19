import pytest
from dbop_core.classify import dbapi_classifier


class OperationalError(Exception):
    """Shape like PyMySQL: args = (errno, message)"""


@pytest.mark.parametrize("errno", [1213, 1205])  # deadlock, lock wait timeout
def test_mysql_errnos_retry(errno):
    e = OperationalError(errno, "mysql transient")
    assert dbapi_classifier(e) is True


@pytest.mark.parametrize(
    "msg",
    [
        "database is locked",  # SQLite
        "Deadlock found when trying to get lock",  # MySQL
        "Lock wait timeout exceeded",  # MySQL
    ],
)
def test_message_based_retry(msg):
    e = Exception(msg)
    assert dbapi_classifier(e) is True


def test_non_transient_returns_false():
    e = Exception("syntax error at or near SELECT")
    assert dbapi_classifier(e) is False

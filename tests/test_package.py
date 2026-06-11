import queryreceipts


def test_version_is_a_string():
    assert isinstance(queryreceipts.__version__, str)

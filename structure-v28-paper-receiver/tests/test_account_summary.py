import pytest

from broker_check import account_summary


def test_account_summary_does_not_expose_account_details():
    result = account_summary([{"account_id": "private-account-id", "account_type": "private-type"}])
    assert result["account_access_confirmed"] is True
    assert result["account_count"] == 1
    assert "private" not in str(result)


@pytest.mark.parametrize("data", [[], {}, {"error_code": "DENIED"}, [None],
                                  [{}], [{"account_id": ""}], [{"account_id": 123}]])
def test_unconfirmed_response_is_rejected(data):
    with pytest.raises(ValueError):
        account_summary(data)

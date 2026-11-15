from common.errors import DeliveryFailedError, ErrorCode


def test_delivery_failed_has_stable_code_and_detail():
    error = DeliveryFailedError("SMTP refused")
    assert error.code is ErrorCode.DELIVERY_FAILED
    assert error.detail == "SMTP refused"

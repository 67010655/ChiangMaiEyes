import ssl

from app.providers.pm25_provider import _air4thai_tls_context


def test_air4thai_certificate_fix_keeps_root_and_hostname_validation():
    context = _air4thai_tls_context()
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert not context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN

from claw_wechat_parser.weixin.cdn import aes_ecb_encrypt_pkcs7


def test_aes_ecb_encrypt_pkcs7_size():
    out = aes_ecb_encrypt_pkcs7(b"abc", b"0" * 16)
    assert len(out) == 16
    out2 = aes_ecb_encrypt_pkcs7(b"a" * 16, b"0" * 16)
    assert len(out2) == 32

import pytest

from ape.types.signatures import MessageSignature, SignableMessage, TransactionSignature


@pytest.fixture
def signable_message():
    version = b"E"
    header = b"thereum Signed Message:\n32"
    body = (
        b"\x86\x05\x99\xc6\xfa\x0f\x05|po(\x1f\xe3\x84\xc0\x0f"
        b"\x13\xb2\xa6\x91\xa3\xb8\x90\x01\xc0z\xa8\x17\xbe'\xf3\x13"
    )
    return SignableMessage(version=version, header=header, body=body)


@pytest.fixture
def signature(owner, signable_message):
    return owner.sign_message(signable_message)


def test_signature_repr():
    signature = TransactionSignature(v=0, r=b"123", s=b"456")
    assert repr(signature) == "<TransactionSignature v=0 r=0x313233 s=0x343536>"


def test_signable_message_repr(signable_message):
    actual = repr(signable_message)
    expected_version = "E"
    expected_header = "thereum Signed Message:\n32"
    expected_body = "0x860599c6fa0f057c706f281fe384c00f13b2a691a3b89001c07aa817be27f313"
    expected = (
        f'SignableMessage(version="{expected_version}", header="{expected_header}", '
        f'body="{expected_body}")'
    )

    assert actual == expected


def test_signature_from_rsv_and_vrs(signature):
    rsv = signature.encode_rsv()
    vrs = signature.encode_vrs()

    # NOTE: Type declaring for sake of ensuring
    #   type-checking works since class-method is
    #   defined in base-class.
    from_rsv: MessageSignature = signature.from_rsv(rsv)
    from_vrs: MessageSignature = signature.from_vrs(vrs)
    assert from_rsv == from_vrs == signature


def test_signable_message_module(signable_message):
    """
    At the time of writing this, SignableMessage is a borrowed
    construct from `eth_account.messages`. We are changing the module
    manually so we are testing that it shows Ape's now.
    """
    actual = signable_message.__module__
    expected = "ape.types.signatures"
    assert actual == expected

    # Also show the 404-causing line in the __doc__ was fixed.
    assert "EIP-191_" not in signable_message.__doc__
    assert "EIP-191" in signable_message.__doc__

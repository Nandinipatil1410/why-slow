from whyslow.platforms.linux import parse_psi_some_avg10


def test_parse_psi():
    text = "some avg10=12.50 avg60=3.10 avg300=0.80 total=123456\nfull avg10=1.00 avg60=0.00 avg300=0.00 total=0\n"
    assert parse_psi_some_avg10(text) == 12.5


def test_parse_psi_missing_line():
    assert parse_psi_some_avg10("") is None

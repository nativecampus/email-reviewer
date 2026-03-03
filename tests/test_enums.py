from app.enums import EmailDirection


class TestEmailDirection:
    def test_values(self):
        assert EmailDirection.EMAIL.value == "EMAIL"
        assert EmailDirection.INCOMING_EMAIL.value == "INCOMING_EMAIL"
        assert EmailDirection.FORWARDED_EMAIL.value == "FORWARDED_EMAIL"

    def test_serialises_as_plain_strings(self):
        assert str(EmailDirection.EMAIL) == "EMAIL"
        assert str(EmailDirection.INCOMING_EMAIL) == "INCOMING_EMAIL"
        assert str(EmailDirection.FORWARDED_EMAIL) == "FORWARDED_EMAIL"

    def test_has_exactly_three_members(self):
        assert len(EmailDirection) == 3

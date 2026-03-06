from app.enums import EmailDirection, JobType


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


class TestJobType:
    def test_includes_chain_build(self):
        assert hasattr(JobType, "CHAIN_BUILD")

    def test_chain_build_serialises_as_string(self):
        assert str(JobType.CHAIN_BUILD) == "Chain_Build"

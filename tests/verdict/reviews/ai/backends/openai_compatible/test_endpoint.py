import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import KEY


@pytest.mark.parametrize("url", ["http://api.airforce/v1", "ftp://x/v1", "api.airforce/v1", "https://", ""])
def test_unsafe_or_malformed_base_urls_are_refused(url):
    with pytest.raises(ai.AIError):
        ai.OpenAIBackend(url, KEY, "m")


def test_the_chat_completions_address_is_built_from_the_base_url_and_local_servers_are_known():
    from verdict.reviews.ai.backends.openai_compatible import Endpoint
    assert Endpoint("https://api.airforce/v1/").chat_completions == "https://api.airforce/v1/chat/completions"
    assert Endpoint("http://host.docker.internal:11434/v1").validated().local and not Endpoint("https://api.airforce/v1").local
    assert Endpoint("").host == ""

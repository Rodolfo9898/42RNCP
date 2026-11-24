"""Stand-ins for the sandbox tests."""


class NoDisplay:
    """The image has no Xvfb: nothing is added to the environment."""

    def environment(self):
        return {}

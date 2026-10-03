class OutcomeUnknown(Exception):
    pass


class PreviewTransport:
    """No network or mailbox access; deterministic local acceptance only."""

    def send(self, delivery):
        return f"preview:{delivery.pk}"


class PreviewActionConnector:
    def execute(self, proposal):
        return f"simulated:{proposal.pk}:{proposal.revision}"

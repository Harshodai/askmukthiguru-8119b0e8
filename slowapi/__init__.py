class Limiter:
    def __init__(self, *args, **kwargs):
        self.enabled = True
        # store any args for potential inspection
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        # placeholder for middleware behavior
        pass

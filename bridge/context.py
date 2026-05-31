class ContextType:
    TEXT = 1
    IMAGE_CREATE = 2
    VOICE = 3


class Context:
    def __init__(self, type=None, content=None):
        self.type = type
        self.content = content
        self.kwargs = {}

    def __getitem__(self, key):
        return self.kwargs.get(key)

    def __setitem__(self, key, value):
        self.kwargs[key] = value

    def get(self, key, default=None):
        return self.kwargs.get(key, default)

    def __contains__(self, key):
        return key in self.kwargs

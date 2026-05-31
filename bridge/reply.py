class ReplyType:
    TEXT = 1
    INFO = 2
    ERROR = 3
    IMAGE_URL = 4
    VOICE = 5


class Reply:
    def __init__(self, type, content):
        self.type = type
        self.content = content

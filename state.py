from datetime import datetime


class AppState:
    def __init__(self):
        self.bot_enabled: bool = True
        self.start_time: datetime = datetime.now()
        self._message_count: int = 0
        self._parser = None

    def record_message(self):
        self._message_count += 1

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def get_parser(self, secret: str):
        if self._parser is None:
            from linebot.v3 import WebhookParser
            self._parser = WebhookParser(secret)
        return self._parser

    def reload_parser(self, secret: str):
        from linebot.v3 import WebhookParser
        self._parser = WebhookParser(secret)


app_state = AppState()

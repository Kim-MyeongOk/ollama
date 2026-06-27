import os
from pathlib          import Path
from logging.handlers import TimedRotatingFileHandler

class CustomFileHandler(TimedRotatingFileHandler):
    def __init__(self, filename, when='M', interval=1, backupCount=0,
                 encoding=None, delay=False, utc=False, atTime=None, errors=None, debug_mode=False):
        self.debug_mode = debug_mode

        filepath = Path(f"./{filename}")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename=filepath, when=when, interval=interval, backupCount=backupCount,
                         encoding=encoding, delay=delay, utc=utc, atTime=atTime, errors=errors)
        if self.debug_mode:
            print(f"mode: {self.mode}", end=', ')
            print(f"filename: {filename}", end=', ')
            print(f"when: {when}", end=', ')
            print(f"interval: {interval}", end=', ')
            print(f"backupCount: {backupCount}", end=', ')
            print(f"encoding: {encoding}", end=', ')
            print(f"delay: {delay}", end=', ')
            print(f"utc: {utc}", end=', ')
            print(f"atTime: {atTime}", end=', ')
            print(f"errors: {errors}")

    def rotation_filename(self, default_name):
        if not callable(self.namer):
            result = default_name
        else:
            result = self.namer(default_name)

        print(f"default_name            : {default_name}")
        print(f"not callable(self.namer): {not callable(self.namer)}")

        return result

    def rotate(self, source, dest):
        if not callable(self.rotator):
            # Issue 18940: A file may not have been created if delay is True.
            if os.path.exists(source):
                os.rename(source, dest)
        else:
            self.rotator(source, dest)

        print(f"source: {source}")
        print(f"dest  : {dest}")

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            # 2. Windows에서 다른 워커 프로세스와 충돌해 PermissionError가 나면
            # 프로세스를 죽이지 않고, 에러를 무시하여 서버가 계속 버티게 만듭니다.
            pass